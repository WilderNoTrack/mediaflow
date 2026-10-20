"""写稿流水线：选题 → 写稿 → 硬检查 + AI 质检 → 不合格就在最好的一版上按意见修改 → 存草稿。

和 v1 最大的区别：这是一条**由代码编排的固定流程**，不是让 LLM 自己决定下一步调什么工具。
写一篇稿子的步骤本来就是确定的，交给 ReAct 只会带来跳步、漏参数、乱填账号 ID。
模型只负责它擅长的部分：出选题、写、评。

手动「立即创作」、管家对话里「写一篇」、自动模式定时写，三个入口都只调 `write_draft`。
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlmodel import Session, col, select

from mediaflow.agents import prompts
from mediaflow.agents.checks import (
    RISKY_WORDS, TAGS_MAX, TITLE_MAX, body_len, body_range, clean_tags, hard_check, shorten_title, strip_meta, tags_min,
    text_len,
)
from mediaflow.agents.context import AccountContext, load_context
from mediaflow.domain.models import (
    Account, Draft, DraftImage, ImageStatus, Topic, TopicStatus, Trigger, utcnow,
)
from mediaflow.llm.client import LLM, LLMError, complete_json
from mediaflow.services.images import can_make
from mediaflow.services.topics import Fetcher, propose_topics

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 4  # 写 1 版 + 最多按质检意见改 3 轮
PASS_SCORE = 7.0

Emit = Callable[[str, str, dict[str, Any] | None], None]


def _noop(stage: str, message: str, data: dict[str, Any] | None = None) -> None:
    pass


@dataclass
class Candidate:
    title: str
    body: str
    tags: list[str]
    image_prompts: list[str]
    issues: list[str] = field(default_factory=list)
    evaluation: dict[str, Any] = field(default_factory=dict)
    score: float | None = None
    changes: list[dict] = field(default_factory=list)  # AI 自己按意见改过的地方（这一版是怎么一步步改出来的）
    note: str = ""  # 写给审核人看的备注（来源、要核实的地方），不进正文、不发出去
    attempted: bool = False  # 这一版的意见有没有交给编辑改过（改过还剩下的，才是「AI 改不好、要人看」的）

    @property
    def items(self) -> list[dict]:
        return [i for i in self.evaluation.get("items") or [] if isinstance(i, dict)]

    @property
    def must(self) -> list[dict]:
        return [i for i in self.items if i.get("level") == "must"]

    @property
    def passed(self) -> bool:
        return (not self.issues and not self.must and not self.evaluation.get("violated_rules")
                and self.score is not None and self.score >= PASS_SCORE)

    def rank(self) -> tuple[int, int, float]:
        # 没有硬伤的优先，其次「必须改」越少越好，再看分数
        return (0 if self.issues else 1, -len(self.must) - len(self.evaluation.get("violated_rules") or []),
                self.score or 0.0)


async def _pick_topic(
    session: Session, llm: LLM, ctx: AccountContext, topic_id: str | None,
    hint: str, emit: Emit, fetch: Fetcher | None,
) -> Topic:
    if topic_id:
        t = session.get(Topic, topic_id)
        if t is None or t.account_id != ctx.account_id:
            raise LookupError("选题不存在或不属于这个账号")
        emit("topic", f"使用选题库里的选题：{t.title}", {"topic_id": t.id, **_topic_info(t)})
        return t
    if not hint:
        # 复刻模式：先按顺序用对标方案里的复刻选题
        bt = session.exec(select(Topic).where(
            Topic.account_id == ctx.account_id, Topic.source == "benchmark", Topic.status == TopicStatus.new,
        ).order_by(col(Topic.created_at))).first()
        if bt is not None:
            emit("topic", f"使用复刻选题：{bt.title}", {"topic_id": bt.id, **_topic_info(bt)})
            return bt
    emit("topic", "正在搜热点、找选题…", None)
    proposal = await propose_topics(session, llm, ctx, direction=hint, count=3, fetch=fetch)
    rep = proposal.report
    ok_src = [st for st in rep.statuses if st.ok and st.count]
    emit("topic", f"热点：{len(ok_src)} 个来源抓到 {len(rep.items)} 条" if rep.items else "热点来源这次没抓到数据",
         {"sources": [{"source": st.source, "label": st.label, "ok": st.ok, "count": st.count, "note": st.note, "mode": st.mode}
                      for st in rep.statuses],
          "hot": [{"source": it.source, "title": it.title[:60], "heat": it.heat, "url": it.url if len(it.url) <= 300 else ""}
                  for it in rep.items[:15]]})
    if proposal.source_note:
        emit("warning", proposal.source_note, None)
    if not proposal.topics:
        if not hint:
            raise LLMError("没能想出和历史内容不重复的选题，换个方向试试")
        # 用户给了具体想法：热点里没挑出新选题时，直接把想法当选题写，而不是报错
        t = Topic(user_id=ctx.user_id, account_id=ctx.account_id, title=hint.strip()[:80], source="user")
        session.add(t)
        session.commit()
        session.refresh(t)
        emit("topic", f"按你的想法写：{t.title}", {"topic_id": t.id})
        return t
    t = proposal.topics[0]
    emit("topic", f"选定选题：{t.title}", {"topic_id": t.id, **_topic_info(t),
                                          "candidates": [_topic_info(x) for x in proposal.topics], "picked": 0,
                                          "skipped_dups": proposal.skipped_duplicates})
    return t


def _topic_info(t: Topic) -> dict:
    return {k: v for k, v in {"title": t.title, "angle": t.angle, "reason": t.reason, "source": t.source,
                              "url": t.source_url}.items() if v}


def _plan_block(plan: list[str]) -> str:
    if not plan:
        return ""
    return (f"\n\n【用户对配图的要求（必须照做）】这篇一共 {len(plan)} 张图，image_prompts 就写 {len(plan)} 张，"
            "第 i 张必须是用户说的那样，只是把画面和图上的字写具体：\n"
            + "\n".join(f"第 {i + 1} 张{'（封面）' if i == 0 else ''}：{p}" for i, p in enumerate(plan)))


def _apply_plan(prompts_: list[str], plan: list[str]) -> list[str]:
    """用户定了每张放什么：张数按用户的，模型漏写的那张直接用用户原话。"""
    if not plan:
        return prompts_
    return [prompts_[i] if i < len(prompts_) and prompts_[i] else plan[i] for i in range(len(plan))]


def _reference_block(ref: dict, *, planned: bool = False) -> str:
    if not ref.get("title"):
        return ""
    posts = [ref, *[x for x in ref.get("extra") or [] if x.get("title")]]

    def one(i: int, p: dict) -> str:
        body = " ".join(str(p.get("content", "")).split())[:600]
        tag = "（主参考帖，配图也照它）" if i == 0 and len(posts) > 1 else ""
        return (f"{i + 1}. {tag}{p.get('creator') or '同领域博主'}，{p.get('likes') or '?'}赞\n标题：{p['title']}\n"
                + (f"正文：{body}\n" if body else "")
                + (f"标签：{'、'.join(p.get('tags') or [])}\n" if p.get("tags") else ""))

    n = len(ref.get("local") or []) or len(ref.get("images") or [])
    imgs = (f"\n\n【配图要和主参考帖一个模子】主参考帖有 {n} 张图，image_prompts 也写 {n} 张，第 i 张对应它的第 i 张"
            "（封面对封面，内页对内页）：出图时会把那张原图当模板，照着它的版式、文字位置、配色和装饰重做，整套用同一份视觉规范，"
            "所以每张只写清「这一张放本篇的什么内容、图上写哪几个字」，信息量和原图那张相当。") if n > 1 and not planned else ""
    learn = ("学它们共同的标题公式、开头钩子、结构节奏和信息密度（以主参考帖为主）" if len(posts) > 1
             else "学它的标题公式、开头钩子、结构节奏和信息密度")
    return ("\n\n" + prompts.UNTRUSTED_NOTICE + "\n<external_data>\n"
            f"【参考帖（{len(posts)} 篇）】\n" + "\n".join(one(i, p) for i, p in enumerate(posts))
            + "</external_data>\n" + learn + "，内容必须换成本账号主题，不照抄任何句子。" + imgs)


async def _generate(llm: LLM, ctx: AccountContext, topic: Topic, hint: str, feedback: str,
                    ref: dict | None = None, plan: list[str] | None = None) -> Candidate:
    data = await complete_json(llm, [
        {"role": "system", "content": prompts.WRITER_SYSTEM},
        {"role": "user", "content": prompts.WRITER_USER.format(
            profile=ctx.profile_text(),
            rules=ctx.rules_text(),
            topic_title=topic.title,
            topic_angle=topic.angle or "自行决定",
            hint_block=f"用户补充要求：{hint}\n" if hint else "",
            feedback_block=f"\n【上一版的问题，这次必须改掉】\n{feedback}\n" if feedback else "",
        ) + _reference_block(ref or (topic.reference or {}), planned=bool(plan)) + _plan_block(plan or [])},
    ], temperature=0.85)
    return Candidate(
        title=str(data.get("title", "")).strip(),
        body=str(data.get("body", "")).strip(),
        tags=clean_tags(data.get("tags") or []),
        image_prompts=_apply_plan([str(p).strip() for p in (data.get("image_prompts") or []) if str(p).strip()][:9], plan or []),
        note=str(data.get("note") or "").strip()[:500],
    )


async def _pick_reference(session: Session, llm: LLM, ctx: AccountContext, topic: Topic, url: str, emit: Emit) -> dict:
    """这篇照着哪些帖子写（配图只照主参考帖）。用户给的链接用不了直接报错（不能悄悄换成别的帖子）；自动挑的挑不到就不用。"""
    from mediaflow.services import refpost

    emit("reference", "找照着做的参考帖…" if not url else "读你给的参考帖…", None)
    try:
        ref, why_none = await refpost.pick(session, llm, ctx.account_id, topic, url=url)
    except refpost.RefError as e:
        raise ValueError(f"参考帖用不了：{e}") from e
    except Exception as e:  # noqa: BLE001 - 自动挑参考帖出问题不影响写稿
        logger.warning("挑参考帖失败", exc_info=True)
        ref, why_none = {}, f"参考帖没找到（{e}）"
    if ref:
        n = len(ref.get("local") or [])
        extra = ref.get("extra") or []
        emit("reference", f"照着「{ref['title'][:24]}」（{ref.get('creator') or '同领域博主'}，{ref.get('likes') or '?'}赞）"
             + (f"等 {1 + len(extra)} 篇" if extra else "") + "写；"
             + (f"配图统一照这篇，{n} 张一张对一张照着原图做" if n else "这篇原图没拿到，配图按账号风格统一出"),
             {"reference": {k: ref.get(k) for k in ("title", "url", "creator", "likes", "source", "why")},
              "images": n,
              "extra": [x.get("title", "") for x in extra],
              "extra_posts": [{k: x.get(k) for k in ("title", "url", "creator", "likes")} for x in extra]})
    else:
        emit("warning", f"{why_none}，这篇按账号的配图风格出图；想照着某篇做，在草稿页贴它的链接", None)
    return ref


def _length_req(ctx: AccountContext) -> str:
    lo, hi = body_range(ctx.rules)
    return f"，规则要求 {lo}–{hi} 字" if lo and hi else f"，规则要求不超过 {hi} 字" if hi else f"，规则要求至少 {lo} 字" if lo else ""


def apply_edits(body: str, edits: list, locked: list[str] | None = None,
                log: list[dict] | None = None) -> tuple[str, int, int]:
    """按「find → replace」定点改正文；返回 (新正文, 改成了几处, 跳过几处)。
    find 必须在正文里原样出现；碰到用户亲手改过的句子就跳过，保住用户的写法。改成的每一处记进 log。"""
    applied = skipped = 0
    for e in edits or []:
        if not isinstance(e, dict):
            continue
        find, rep = str(e.get("find") or ""), str(e.get("replace") if e.get("replace") is not None else "")
        if not find.strip() or find == rep:
            continue
        pos = body.find(find)
        if pos < 0 and find.strip() != find:
            find = find.strip()
            pos = body.find(find)
        if pos < 0:
            skipped += 1
            continue
        end = pos + len(find)
        if any((lp := body.find(s)) >= 0 and lp < end and pos < lp + len(s) for s in locked or []):
            skipped += 1
            continue
        body = body[:pos] + rep + body[end:]
        applied += 1
        if log is not None:
            log.append({"find": find, "replace": rep, "item": e.get("item")})
    return body.strip(), applied, skipped


_SENT = re.compile(r"[^。！？!?\n]+[。！？!?]?")


def user_sentences(original: str, current: str) -> list[str]:
    """用户亲手改过/新写的句子：现在正文里有、AI 原稿里没有的句子。"""
    if not original or original == current:
        return []
    orig = {x.strip() for x in _SENT.findall(original)}
    return [x.strip() for x in _SENT.findall(current) if len(x.strip()) >= 4 and x.strip() not in orig][:30]


async def _fit_title(llm: LLM, ctx: AccountContext, c: Candidate) -> str:
    """标题超过 20 字的不靠模型自觉：让它一次给 5 个短的，代码数字数，挑第一个合格的；都不合格带上字数再要一次；
    还不行按标点截短。返回改动说明（没改返回空）。"""
    if text_len(c.title) <= TITLE_MAX:
        return ""
    old, n = c.title, text_len(c.title)
    bad: list[str] = []
    for _ in range(2):
        retry = ("上次给的都超了（" + "；".join(f"{t}（{text_len(t)} 字）" for t in bad[:5])
                 + f"），这次每个必须不超过 {TITLE_MAX - 4} 个字，数清楚再给。\n") if bad else ""
        try:
            data = await complete_json(llm, [
                {"role": "system", "content": prompts.TITLE_FIT_SYSTEM.format(limit=TITLE_MAX - 2)},
                {"role": "user", "content": prompts.TITLE_FIT_USER.format(
                    rules=ctx.rules_text(), title=old, n=n, body=c.body[:200], retry=retry)},
            ], temperature=0.6)
        except LLMError:
            logger.warning("改短标题失败", exc_info=True)
            break
        got = [str(t).strip().strip("「」\"") for t in data.get("titles") or [] if str(t).strip()]
        ok = [t for t in got if 4 <= text_len(t) <= TITLE_MAX and not any(w in t for w in RISKY_WORDS)]
        if ok:
            c.title = ok[0]
            break
        bad = got or bad
    if text_len(c.title) > TITLE_MAX:
        c.title = shorten_title(old)
    why = f"标题 {n} 字超过小红书上限 {TITLE_MAX} 字，自动改短到 {text_len(c.title)} 字"
    # 封面描述里照抄了原标题的大字也跟着换，不然图上还是那句长的
    c.image_prompts = [p.replace(f"「{old}」", f"「{c.title}」") for p in c.image_prompts]
    c.changes = [*c.changes, {"where": "标题", "before": old, "after": c.title, "why": why}]
    return why


def _fit_tags(ctx: AccountContext, c: Candidate) -> None:
    """标签个数由代码定：多了留前 10 个，少了从账号关键词里补。"""
    lo = tags_min(ctx.rules)
    tags = c.tags[:TAGS_MAX]
    for k in ctx.keywords:
        if len(tags) >= lo:
            break
        k = k.strip().lstrip("#")
        if k and k not in tags:
            tags.append(k[:20])
    c.tags = tags


async def _enforce(llm: LLM, ctx: AccountContext, c: Candidate, emit: Emit) -> None:
    """平台硬限制（标题 20 字、标签个数）交给代码落实，模型写出来的每一版都过一遍，保证听话。"""
    body, moved = strip_meta(c.body)
    if moved:
        c.body = body
        c.note = "\n".join(x for x in (c.note, *moved) if x)[:800]
        c.changes = [*c.changes, *({"where": "正文", "before": m[:200], "after": "",
                                    "why": "这句是写给审核人看的说明，不该发出去，挪到了备注"} for m in moved)]
        emit("write", f"正文里有 {len(moved)} 句写给审核人看的说明，挪到备注里了", {"moved": moved})
    why = await _fit_title(llm, ctx, c)
    if why:
        ch = c.changes[-1] if c.changes else {}
        emit("write", f"{why}：{c.title}", {"title_fit": {"before": ch.get("before", ""), "after": c.title}})
    _fit_tags(ctx, c)


def _version(c: Candidate, base: Candidate | None = None) -> dict:
    """进度事件里带上这一版的样子和这一轮改了什么，对话里能看到完整的写作过程。"""
    new = c.changes[len(base.changes):] if base is not None and len(c.changes) >= len(base.changes) else c.changes
    clip = lambda x: str(x or "")[:160]  # noqa: E731
    return {"title": c.title, "body_len": body_len(c.body), "tags": c.tags[:10], "images": len(c.image_prompts),
            "changes": [{"where": clip(x.get("where")), "before": clip(x.get("before")), "after": clip(x.get("after")),
                         "why": clip(x.get("why"))} for x in new[:12] if isinstance(x, dict)]}


def _n_problems(c: Candidate) -> int:
    return len(c.issues) + len(c.evaluation.get("violated_rules") or []) + len(c.must)


def _unchanged(a: Candidate, b: Candidate) -> bool:
    return (a.title, a.body, a.tags, a.image_prompts) == (b.title, b.body, b.tags, b.image_prompts)


def _locked_block(locked: list[str], title_locked: bool) -> str:
    lines = ([f"- 标题（用户改过）"] if title_locked else []) + [f"- {x}" for x in locked[:20]]
    return prompts.LOCKED_BLOCK.format(locked="\n".join(lines)) if lines else ""


def _change_why(item, entries: list[dict]) -> tuple[str, str]:
    try:
        e = entries[int(item) - 1]
        return e.get("where", ""), e.get("problem", "")
    except (TypeError, ValueError, IndexError):
        return "", ""


async def _revise(llm: LLM, ctx: AccountContext, c: Candidate, feedback: str, *,
                  locked: list[str] | None = None, title_locked: bool = False,
                  entries: list[dict] | None = None) -> Candidate:
    """在已有的一版上定点修改（find → replace），由代码落到原文上：没被点名的句子一个字不动，
    用户亲手改过的句子也不会被冲掉。模型要是回了整篇（老格式），也接得住。"""
    data = await complete_json(llm, [
        {"role": "system", "content": prompts.REVISER_SYSTEM},
        {"role": "user", "content": prompts.REVISER_USER.format(
            profile=ctx.profile_text(), rules=ctx.rules_text(), title=c.title, body=c.body,
            body_len=body_len(c.body), length_req=_length_req(ctx), tags="、".join(c.tags),
            images="\n".join(f"{i + 1}. {p}" for i, p in enumerate(c.image_prompts)) or "（无）",
            locked_block=_locked_block(locked or [], title_locked),
            feedback=feedback or "- 整体再打磨一遍：开头更抓人、信息更具体",
        )},
    ], temperature=0.4)
    log: list[dict] = []
    if isinstance(data.get("edits"), list):
        body, applied, skipped = apply_edits(c.body, data["edits"], locked, log)
    else:
        body, applied, skipped = (str(data.get("body", "")).strip() or c.body), 0, 0
    title = str(data.get("title") or "").strip() or c.title
    if title_locked and title != c.title and not any("标题" in i for i in c.issues):
        title = c.title  # 用户改过的标题不动，除非标题本身有硬伤（比如超字数）
    out = Candidate(
        title=title, body=body or c.body,
        tags=clean_tags(data.get("tags") or []) or c.tags,
        image_prompts=[str(p).strip() for p in (data.get("image_prompts") or []) if str(p).strip()][:9] or c.image_prompts,
    )
    out.note = c.note
    out.evaluation = {"edits": {"applied": applied, "skipped": skipped,
                                "unfixed": [str(x) for x in data.get("unfixed") or []][:3]}}
    new: list[dict] = []
    for x in log:
        where, why = _change_why(x.get("item"), entries or [])
        new.append({"where": where or "正文", "before": x["find"][:200], "after": x["replace"][:200], "why": why[:120]})
    if out.title != c.title:
        new.append({"where": "标题", "before": c.title, "after": out.title, "why": _why_for("标题", entries)})
    if out.tags != c.tags:
        new.append({"where": "标签", "before": "、".join(c.tags), "after": "、".join(out.tags), "why": _why_for("标签", entries)})
    for i, p in enumerate(out.image_prompts):
        old = c.image_prompts[i] if i < len(c.image_prompts) else ""
        if p != old:
            new.append({"where": f"配图{i + 1}", "before": old[:200], "after": p[:200], "why": _why_for(f"配图{i + 1}", entries)})
    out.changes = [*c.changes, *new]
    return out


def _why_for(where: str, entries: list[dict] | None) -> str:
    return next((e.get("problem", "")[:120] for e in entries or [] if where in (e.get("where") or "")), "")


async def _check(llm: LLM, ctx: AccountContext, c: Candidate, *, prev: Candidate | None = None,
                 locked: list[str] | None = None, title_locked: bool = False, final: bool = False) -> bool:
    """硬检查 + AI 质检；prev 是上一版（复核模式：主编先核对上一轮的问题改好没有）。返回质检是否出错。"""
    c.issues = hard_check(c.title, c.body, c.tags, c.image_prompts, ctx.rules)
    try:
        await _evaluate(llm, ctx, c, prev=prev, locked=locked or [], title_locked=title_locked, final=final)
        return False
    except LLMError:
        logger.warning("质检失败", exc_info=True)
        return True


def _next_base(cands: list[Candidate]) -> Candidate:
    """下一轮在哪一版上改：最新一版分数更高、只是带了硬伤（比如标题超字数）时，在它上面把硬伤改掉更容易收敛；
    否则回到目前最好的一版，免得越改越偏。最终留哪版仍按 rank（没硬伤优先，再看分数）。"""
    best, last = max(cands, key=lambda x: x.rank()), cands[-1]
    return last if (last.score or 0) > (best.score or 0) else best


def _problems(c: Candidate) -> str:
    items = [*c.issues, *(f"没遵守：{r[:24]}" for r in c.evaluation.get("violated_rules", [])),
             *(f"{i.get('where', '')}：{i.get('problem', '')}" for i in c.must)]
    if not items:
        return ""
    return f"，还有 {len(items)} 处要改（{items[0][:30]}{'…' if len(items) > 1 else ''}）"


def _sig(title: str, body: str) -> str:
    import hashlib
    return hashlib.sha1(f"{title}\n{body}".encode()).hexdigest()[:12]


def _history(cands: list[Candidate], start: int = 1) -> list[dict]:
    return [{"attempt": start + i, "score": c.score,
             "problems": len(c.issues) + len(c.evaluation.get("violated_rules", [])) + len(c.must)}
            for i, c in enumerate(cands)]


def _item_text(i: dict) -> str:
    q = f"「{str(i.get('quote', ''))[:40]}」" if i.get("quote") else ""
    return f"{i.get('where') or '全文'}{q}：{i.get('problem', '')}"


def _prev_block(prev: Candidate | None, final: bool = False) -> str:
    rows = [f"{n}. [硬伤] {x}" for n, x in enumerate(prev.issues, 1)] if prev else []
    if prev:
        rows += [f"{len(rows) + n}. [{'必须改' if i.get('level') == 'must' else '可以更好'}] {_item_text(i)}"
                 for n, i in enumerate(prev.items, 1)]
    mode = prompts.EVAL_MODE_FINAL if final else prompts.EVAL_MODE_REVIEW
    return prompts.EVAL_REVIEW_BLOCK.format(prev="\n".join(rows), mode_note=mode) if rows else ""


async def _evaluate(llm: LLM, ctx: AccountContext, c: Candidate, *, prev: Candidate | None = None,
                    locked: list[str] | None = None, title_locked: bool = False, final: bool = False) -> None:
    data = await complete_json(llm, [
        {"role": "system", "content": prompts.EVALUATOR_SYSTEM},
        {"role": "user", "content": prompts.EVALUATOR_USER.format(
            profile=ctx.profile_text(),
            rules=ctx.rules_text(),
            title=c.title,
            body=c.body,
            body_len=body_len(c.body),
            tags="、".join(c.tags),
            images="\n".join(f"{i + 1}. {p}" for i, p in enumerate(c.image_prompts)) or "（无）",
            locked_block=_locked_block(locked or [], title_locked), review_block=_prev_block(prev, final),
        )},
    ], temperature=0.2)
    dims = {}
    for k in ("hook", "value", "voice", "fit", "rules"):
        try:
            dims[k] = max(0.0, min(10.0, float(data.get(k, 0))))
        except (TypeError, ValueError):
            dims[k] = 0.0
    # 分数由代码算，不信模型自己报的总分；规则没遵守直接封顶
    score = round(sum(dims.values()) / len(dims), 1)
    violated = [str(v) for v in data.get("violated_rules") or [] if str(v).strip()]
    if violated:
        score = min(score, 6.0)
    items = []
    for it in data.get("items") or []:
        if isinstance(it, dict) and str(it.get("problem", "")).strip():
            items.append({"level": "must" if str(it.get("level", "")).lower().startswith("must") else "nice",
                          **{k: str(it.get(k, "")).strip()[:300] for k in ("where", "quote", "problem", "fix")}})
    # 兼容老格式：只给了 issues / suggestions 字符串
    items += [{"level": "nice", "where": "", "quote": "", "problem": str(x), "fix": ""} for x in data.get("issues") or []
              if str(x).strip() and not data.get("items")]
    must = [i for i in items if i["level"] == "must"][:3]
    nice = [i for i in items if i["level"] == "nice"][:3]
    c.score = score
    c.evaluation = {
        **({"edits": c.evaluation["edits"]} if c.evaluation.get("edits") else {}),
        "dimensions": dims,
        "violated_rules": violated,
        "items": must + nice,
        "resolved": len([x for x in data.get("resolved") or [] if str(x).strip()]),
        "issues": [_item_text(i) for i in must + nice],
        "suggestions": [str(x) for x in data.get("suggestions") or []],
    }


def _feedback_entries(c: Candidate, note: str = "", *, include_nice: bool = True) -> list[dict]:
    """给改稿编辑的意见（每条带位置，方便把改动和原因对上）：用户的要求 > 硬伤 > 没遵守的规则 > 必须改 > 可以更好。
    主编提的每条意见都有具体改法，所以默认全部交给编辑落实——提了就改，而不是只列出来让人自己改。"""
    ev = c.evaluation
    out = [{"text": f"用户的要求：{note.strip()}", "where": "", "problem": note.strip()}] if note.strip() else []
    out += [{"text": f"[硬伤] {i}", "where": "标题" if "标题" in i else "标签" if "标签" in i else "", "problem": i} for i in c.issues]
    out += [{"text": f"[没遵守规则] {r}", "where": "", "problem": f"没遵守：{r}"} for r in ev.get("violated_rules", [])]
    key = c.items if include_nice else (c.must or ([] if out else c.items))
    for i in key:
        fix = f"｜改法：{i['fix']}" if i.get("fix") else ""
        out.append({"text": f"[{'必须改' if i.get('level') == 'must' else '可以更好'}] {_item_text(i)}{fix}",
                    "where": i.get("where", ""), "problem": i.get("problem", "")})
    if not c.items:  # 老格式
        out += [{"text": f"[建议] {x}", "where": "", "problem": x} for x in ev.get("suggestions", [])]
    return out


def _feedback_for(c: Candidate, note: str = "", *, include_nice: bool = True) -> str:
    return "\n".join(f"{n}. {e['text']}" for n, e in enumerate(_feedback_entries(c, note, include_nice=include_nice), 1))


def _actionable(c: Candidate) -> bool:
    """还有没有能交给编辑改的意见（硬伤、没守的规则、主编的意见，不管必须改还是可以更好）。"""
    low = c.score is not None and c.score < PASS_SCORE
    return bool(c.issues or c.evaluation.get("violated_rules") or c.items or low)


def _stored_eval(c: Candidate, history: list[dict]) -> dict:
    return {**c.evaluation, "history": history, "checked": _sig(c.title, c.body),
            "changes": c.changes[-40:], "attempted": c.attempted, **({"editor_note": c.note} if c.note else {})}


async def write_draft(
    session: Session,
    llm: LLM,
    account_id: str,
    *,
    topic_id: str | None = None,
    hint: str = "",
    trigger: Trigger = Trigger.manual,
    emit: Emit = _noop,
    fetch: Fetcher | None = None,
    reference_url: str = "",
    image_plan: list[str] | None = None,
) -> Draft:
    ctx = load_context(session, account_id)
    if not (ctx.theme or ctx.keywords or hint or topic_id):
        raise ValueError("账号还没有设定主题，先和管家聊聊账号定位吧")

    topic = await _pick_topic(session, llm, ctx, topic_id, hint, emit, fetch)
    ref = await _pick_reference(session, llm, ctx, topic, reference_url, emit)

    candidates: list[Candidate] = []
    eval_failed = False
    emit("write", "第 1 版写作中…", {"attempt": 1, "topic": topic.title})
    plan = [p.strip() for p in image_plan or [] if p.strip()][:9]
    c = await _generate(llm, ctx, topic, hint, "", ref, plan)
    await _enforce(llm, ctx, c, emit)
    if await _check(llm, ctx, c):
        eval_failed = True
        emit("warning", "质检服务出错，这一版没有经过 AI 质检", None)
    candidates.append(c)
    emit("review", f"第 1 版：{c.score if c.score is not None else '未评分'} 分" + _problems(c),
         {"attempt": 1, "score": c.score, "issues": c.issues, "evaluation": c.evaluation, **_version(c)})
    # AI 提的意见由 AI 自己落实：有意见就交给编辑改，改完复核；最后一轮只复核不再提新意见，
    # 这样留在稿子上的意见一定是「改过但没改好」的，不会出现提了却没人改。
    for attempt in range(2, MAX_ATTEMPTS + 1):
        base = _next_base(candidates)
        if not _actionable(base):
            break
        entries = _feedback_entries(base)
        base.attempted = True
        emit("write", f"按 AI 的 {len(entries)} 条意见自动改第 {attempt - 1} 轮…",
             {"attempt": attempt, "feedback": [e["text"][:200] for e in entries]})
        try:
            c = await _revise(llm, ctx, base, _feedback_for(base), entries=entries)
        except LLMError as e:
            emit("warning", f"第 {attempt} 版生成失败（{e}），使用已有的最好版本", None)
            break
        await _enforce(llm, ctx, c, emit)
        if _unchanged(c, base):
            emit("warning", "这一轮编辑没找到能改的地方，用已有的最好版本", None)
            break
        if await _check(llm, ctx, c, prev=base, final=attempt == MAX_ATTEMPTS):
            eval_failed = True
            emit("warning", "质检服务出错，这一版没有经过 AI 质检", None)
        candidates.append(c)
        emit("review", f"改第 {attempt - 1} 轮：{c.score if c.score is not None else '未评分'} 分" + _problems(c),
             {"attempt": attempt, "score": c.score, "issues": c.issues, "evaluation": c.evaluation, **_version(c, base)})

    best = max(candidates, key=lambda x: x.rank())
    needs_attention = bool(best.issues) or best.score is None or best.score < PASS_SCORE or eval_failed
    if needs_attention:
        emit("warning", "没有一版完全达标，已保存最好的一版，并标记为需要重点检查", None)

    best.evaluation = _stored_eval(best, _history(candidates))
    draft = Draft(
        user_id=ctx.user_id,
        account_id=ctx.account_id,
        topic_id=topic.id,
        title=best.title,
        body=best.body,
        tags=best.tags,
        original_title=best.title,
        original_body=best.body,
        trigger=trigger,
        score=best.score,
        evaluation=best.evaluation,
        check_issues=best.issues,
        attempts=len(candidates),
        needs_attention=needs_attention,
        reference=ref,
    )
    session.add(draft)
    session.flush()
    status = ImageStatus.pending if can_make(session.get(Account, account_id)) else ImageStatus.skipped
    if plan:  # 改稿时模型可能动了配图描述：张数和每张要什么，还是以用户说的为准
        best.image_prompts = _apply_plan(best.image_prompts, plan)
    for i, p in enumerate(best.image_prompts):
        session.add(DraftImage(draft_id=draft.id, idx=i, prompt=p, status=status))
    topic.status = TopicStatus.used
    session.add(topic)
    draft.updated_at = utcnow()
    session.commit()
    session.refresh(draft)
    emit("done", f"草稿已保存：{draft.title}", {"draft_id": draft.id, "score": draft.score})
    return draft


async def revise_draft(session: Session, llm: LLM, draft_id: str, *, note: str = "", emit: Emit = _noop,
                       rounds: int = 2) -> Draft:
    """按当前质检意见（和用户补充的要求）在草稿上再改 1-2 轮，改好了才替换；没改好保留原稿。"""
    draft = session.get(Draft, draft_id)
    if draft is None:
        raise LookupError("草稿不存在")
    ctx = load_context(session, draft.account_id)
    images = sorted(session.exec(select(DraftImage).where(DraftImage.draft_id == draft.id)).all(), key=lambda i: i.idx)
    cur = Candidate(title=draft.title, body=draft.body, tags=list(draft.tags), image_prompts=[i.prompt for i in images],
                    issues=list(draft.check_issues), evaluation=dict(draft.evaluation or {}), score=draft.score,
                    changes=list((draft.evaluation or {}).get("changes") or []),
                    note=str((draft.evaluation or {}).get("editor_note") or ""))
    locked = user_sentences(draft.original_body, draft.body)
    title_locked = draft.title != draft.original_title
    if note.strip() or cur.score is None or cur.evaluation.get("checked") != _sig(cur.title, cur.body):
        # 用户改过稿子或提了新要求：先按现在的版本重新质检，意见才对得上（用户改过的句子不挑措辞）
        await _check(llm, ctx, cur, locked=locked, title_locked=title_locked)
    history = list((draft.evaluation or {}).get("history") or [])
    if not history and cur.score is not None:  # 老稿子没有记录：把改之前的版本记上，分数变化才看得出来
        history = [{"attempt": draft.attempts, "score": cur.score, "problems": len(cur.issues)}]
    start = (history[-1]["attempt"] + 1) if history else draft.attempts + 1
    tried: list[Candidate] = []
    best = cur
    for r in range(rounds):
        base = _next_base([cur, *tried])
        entries = _feedback_entries(base, note)
        emit("write", f"按质检意见再改第 {r + 1} 轮…", {"attempt": start + r, "feedback": [e["text"][:200] for e in entries]})
        base.attempted = True
        try:
            c = await _revise(llm, ctx, base, _feedback_for(base, note), entries=entries,
                              locked=locked, title_locked=title_locked)
        except LLMError as e:
            if tried:
                emit("warning", f"这一轮没改成（{e}），用已经改好的版本", None)
                break
            raise
        await _enforce(llm, ctx, c, emit)
        if _unchanged(c, base):
            emit("warning", "这一轮编辑没找到能改的地方，停下来", None)
            break
        await _check(llm, ctx, c, prev=base, locked=locked, title_locked=title_locked, final=r == rounds - 1)
        tried.append(c)
        emit("review", f"改第 {r + 1} 轮：{c.score if c.score is not None else '未评分'} 分" + _problems(c),
             {"attempt": start + r, "score": c.score, "issues": c.issues, "evaluation": c.evaluation, **_version(c, base)})
        # 更好就换；用户明确提了要求时，只要不比原来差也换（用户要的就是这个改动）
        if c.rank() > best.rank() or (note.strip() and best is cur and c.rank() >= cur.rank()):
            best = c
        if not _actionable(c) and (not note.strip() or best is c):
            break
    history += _history(tried, start)
    improved = best is not cur
    if improved:
        draft.title, draft.body, draft.tags = best.title, best.body, best.tags
        for i, img in enumerate(images):
            if i < len(best.image_prompts) and img.prompt != best.image_prompts[i] and img.status != ImageStatus.done:
                img.prompt = best.image_prompts[i]
                session.add(img)
    draft.score, draft.check_issues = best.score, best.issues
    draft.evaluation = _stored_eval(best, history)
    draft.attempts += len(tried)
    draft.needs_attention = not best.passed
    draft.updated_at = utcnow()
    session.add(draft)
    session.commit()
    session.refresh(draft)
    if improved:
        before, after = _n_problems(cur), _n_problems(best)
        fixed = f"，要改的问题 {before} → {after} 处" if before != after else ""
        msg = (f"改好了：{cur.score if cur.score is not None else '?'} → {draft.score} 分{fixed}"
               if (best.score or 0) != (cur.score or 0) or not fixed else f"改好了：分数不变（{draft.score}）{fixed}")
        if note.strip() and not fixed and (best.score or 0) == (cur.score or 0):
            msg = f"按你的要求改好了（{draft.score} 分）"
    else:
        top = max(tried, key=lambda x: x.score or 0) if tried else None
        why = (f"改出来最高 {top.score} 分，但还有硬伤（{top.issues[0][:30]}），" if top and top.issues and (top.score or 0) > (cur.score or 0)
               else "改出来的分数没有更高，")
        msg = f"{why}所以保留原稿（{draft.score} 分）。可以补一句要求再试，或者自己改"
    emit("done", msg, {"draft_id": draft.id})
    return draft
