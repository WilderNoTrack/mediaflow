"""账号配图模板：看对标账号的一批图（多模态模型），总结出「整体视觉 + 几种页型（各配样例图）」，存在 Account.visual。

有模板之后：
- 写稿时告诉写手这个账号有哪几种页，配图描述照着页型写；
- 出图时每张选一种页型，带上该页型的样例图当版式模板、整体视觉当统一规范 → 每篇的图都像同一个博主出的；
- 用户自己给了参考帖的那篇例外：配图照用户给的那篇做。

学模板要能看图（DeepSeek 的多模态模型，同一个 Key）；看不了图就不学，出图照旧按每篇的参考帖来。
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
from collections.abc import Callable
from typing import Any

from sqlmodel import Session

from mediaflow.agents import prompts
from mediaflow.config import get_settings
from mediaflow.domain.models import Account, utcnow
from mediaflow.llm.client import LLM, LLMError, complete_json, get_vision_llm, image_part
from mediaflow.research.types import count_num
from mediaflow.services.refs import cache_local

logger = logging.getLogger(__name__)

Emit = Callable[[str, str, dict | None], None]
MAX_IMAGES = 16  # 一次最多看几张（每张约几百 token）
FULL_POSTS = 3  # 看全套图（封面 + 内页）的帖子数，其余只看封面
INNER_PER_POST = 4
MAX_PAGES = 6
VISION_SIDE = 768  # 给看图模型的图压到这么大，够看清版式和字


class VisualError(RuntimeError):
    pass


def _noop(stage: str, message: str, data: dict | None = None) -> None:
    pass


# ── 读模板 ─────────────────────────────────────────────────────────────


def pages(visual: dict | None) -> list[dict]:
    return [p for p in (visual or {}).get("pages") or [] if isinstance(p, dict) and p.get("type")]


def has_template(acc: Account | None) -> bool:
    return bool(acc and (acc.visual or {}).get("spec") and pages(acc.visual))


def _exists(rel: str) -> bool:
    return bool(rel) and (get_settings().images_dir / rel).exists()


def page_for(visual: dict, type_name: str, idx: int) -> dict | None:
    """这张用哪种页：按名字找（容忍「清单」「清单页」这种差一点的），封面固定用封面那种，找不到用第一种非封面页。"""
    ps = pages(visual)
    if not ps:
        return None
    cover = next((p for p in ps if "封面" in p["type"]), ps[0])
    if idx == 0:
        return cover
    t = (type_name or "").strip()
    inner = [p for p in ps if p is not cover] or ps
    exact = next((p for p in inner if p["type"] == t), None)
    if exact:
        return exact
    fuzzy = next((p for p in inner if t and (t in p["type"] or p["type"] in t)), None)
    return fuzzy or inner[(idx - 1) % len(inner)]


def example_of(page: dict | None) -> str:
    """页型的样例图（本地缓存路径）；样例都没了返回空。"""
    for rel in (page or {}).get("examples") or []:
        if _exists(rel):
            return rel
    return ""


def template_block(visual: dict) -> str:
    """给「一套图提示词」那一步的模板说明。"""
    lines = [f"- {p['type']}：{p.get('desc', '')}" + (f"（适合：{p['when']}）" if p.get("when") else "") for p in pages(visual)]
    return prompts.IMAGE_TEMPLATE_BLOCK.format(spec=visual.get("spec", ""), pages="\n".join(lines))


def context_line(visual: dict | None) -> str:
    """给写手看的一行：这个账号的图有哪几种页，配图描述照页型写。"""
    ps = pages(visual)
    if not ps or not (visual or {}).get("spec"):
        return ""
    kinds = "；".join(f"{p['type']}" + (f"（{p['when']}）" if p.get("when") else "") for p in ps)
    return (f"配图模板（整个账号统一照它出图）：{str(visual['spec'])[:160]}。页型：{kinds}。"
            "写配图描述时每张开头标上用哪种页，比如「清单页：…」")


# ── 学模板 ─────────────────────────────────────────────────────────────


def _posts_from_benchmarks(s: Session, acc: Account) -> list[dict]:
    from mediaflow.services import benchmark as bench

    groups = []
    for b in bench.ready(s, acc.id):
        out = []
        for x in b.samples or []:
            if x.get("kind") == "视频":
                continue
            imgs = [u for u in x.get("images") or [] if u] or ([x["cover"]] if x.get("cover") else [])
            if imgs:
                out.append({"title": x.get("title", ""), "url": x.get("url", ""), "likes": x.get("likes", ""),
                            "creator": b.creator_name, "images": imgs})
        out.sort(key=lambda p: (len(p["images"]) <= 1, -count_num(p.get("likes"))))  # 有全套图的、赞多的在前
        groups.append(out)
    full = bench.interleave([[p for p in g if len(p["images"]) > 1] for g in groups])  # 几个对标轮流取，不只看一个人的
    return full + bench.interleave([[p for p in g if len(p["images"]) <= 1] for g in groups])


async def _posts_from_links(links: list[str]) -> list[dict]:
    from mediaflow.services import refpost

    out = []
    for i, u in enumerate(links[:5]):
        try:
            d = await refpost._read(u, need_images=True)
        except refpost.RefError as e:
            raise VisualError(f"第 {i + 1} 个链接：{e}" if len(links) > 1 else str(e)) from e
        imgs = [x for x in d.get("images") or [] if x] or ([d["cover"]] if d.get("cover") else [])
        if imgs:
            out.append({"title": d.get("title", ""), "url": d.get("url", u), "likes": d.get("likes", ""),
                        "creator": d.get("creator", ""), "images": imgs})
    return out


async def _gather(posts: list[dict]) -> list[tuple[str, str]]:
    """挑要看的图并缓存到本地：前几篇看全套（封面 + 内页），其余只看封面。返回 [(说明, 本地路径)]。"""
    full = [p for p in posts if len(p["images"]) > 1][:FULL_POSTS]
    picked: list[tuple[str, str]] = []
    for p in full:
        for k, u in enumerate(p["images"][: 1 + INNER_PER_POST]):
            picked.append((f"「{p['title'][:24]}」{'封面' if k == 0 else f'第 {k + 1} 张'}", u))
    for p in posts:
        if len(picked) >= MAX_IMAGES:
            break
        if p not in full:
            picked.append((f"「{p['title'][:24]}」封面", p["images"][0]))
    out = []
    for label, u in picked[:MAX_IMAGES]:
        got = await cache_local([u])
        if got:
            out.append((label, got[0]))
    return out


async def _refresh(posts: list[dict]) -> list[dict]:
    """存的原图地址过期了（小红书图片链接带时间戳）：有笔记链接的重新读一遍拿新地址。"""
    from mediaflow.services import refpost

    out = []
    for p in posts[:FULL_POSTS + 2]:
        if not p.get("url"):
            continue
        try:
            d = await refpost._detail(p["url"])
        except Exception as e:  # noqa: BLE001
            logger.info("对标原图重新读取失败 %s：%s", p["url"][:60], e)
            continue
        if d.get("images"):
            out.append({**p, "images": d["images"]})
    return out


def _vision_uri(rel: str) -> str | None:
    from PIL import Image

    path = get_settings().images_dir / rel
    if not path.exists():
        return None
    try:
        im = Image.open(path).convert("RGB")
        im.thumbnail((VISION_SIDE, VISION_SIDE))
        b = io.BytesIO()
        im.save(b, "JPEG", quality=82)
    except Exception:  # noqa: BLE001
        return None
    import base64

    return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()


def _clean(raw: Any, shots: list[tuple[str, str]], old: dict | None = None) -> dict:
    """模型给的模板 → 规整：页型去重、封面放第一、图号换成本地样例路径（新页型没样例时沿用同名旧页型的）。"""
    if not isinstance(raw, dict):
        raise VisualError("看图模型没给出模板")
    spec = " ".join(str(raw.get("spec") or "").split())[:400]
    old_ex = {p["type"]: p.get("examples") or [] for p in pages(old)}
    out_pages: list[dict] = []
    seen: set[str] = set()
    for p in raw.get("pages") or []:
        if not isinstance(p, dict):
            continue
        t = " ".join(str(p.get("type") or "").split())[:12]
        if not t or t in seen:
            continue
        seen.add(t)
        ex = []
        for n in p.get("examples") or []:
            try:
                k = int(str(n).strip().lstrip("图")) - 1
            except ValueError:
                continue
            if 0 <= k < len(shots) and shots[k][1] not in ex:
                ex.append(shots[k][1])
        out_pages.append({"type": t, "desc": " ".join(str(p.get("desc") or "").split())[:160],
                          "when": " ".join(str(p.get("when") or "").split())[:60],
                          "examples": ex[:3] or old_ex.get(t, [])[:3]})
    if not spec or not out_pages:
        raise VisualError("看图模型没总结出模板，换几篇图文多的对标再试")
    out_pages.sort(key=lambda p: "封面" not in p["type"])
    if "封面" not in out_pages[0]["type"]:
        out_pages.insert(0, {"type": "封面", "desc": "", "when": "每篇第 1 张",
                             "examples": [shots[0][1]] if shots else []})
    tips = [" ".join(str(x).split())[:60] for x in raw.get("tips") or [] if str(x).strip()][:3]
    return {"spec": spec, "pages": out_pages[:MAX_PAGES], "tips": tips}


async def learn(s: Session, account_id: str, *, links: list[str] | None = None, emit: Emit = _noop,
                vision: LLM | None = None) -> dict:
    """学配图模板：给了链接就照这几篇学，否则看对标账号的爆款图。学好存进 Account.visual。"""
    acc = s.get(Account, account_id)
    if acc is None:
        raise LookupError("账号不存在")
    vllm = vision or get_vision_llm()
    if vllm is None:
        raise VisualError("现在用的模型看不了图，学不了配图模板（需要 DeepSeek Key 和看图模型）")
    if links:
        emit("visual", f"在读你给的 {len(links)} 篇笔记的图…", None)
        posts = await _posts_from_links(links)
        source = {"kind": "links", "names": sorted({p["creator"] for p in posts if p.get("creator")}),
                  "links": links[:5]}
    else:
        posts = _posts_from_benchmarks(s, acc)
        if not posts:
            raise VisualError("还没有学好的对标账号（或对标只发视频），先加对标，或者直接给几篇图文笔记链接")
        source = {"kind": "benchmarks", "names": sorted({p["creator"] for p in posts if p.get("creator")})}
    shots = await _gather(posts)
    if len(shots) < 4 and not links:
        emit("visual", "存的原图地址过期了，重新读几篇对标爆款的图…", None)
        fresh = await _refresh(posts)
        if fresh:
            shots = await _gather(fresh + [p for p in posts if p["url"] not in {f["url"] for f in fresh}])
    if len(shots) < 2:
        raise VisualError("对标账号的原图拿不到（可能要小红书登录态），配图模板没学成")
    emit("visual", f"在看 {len(shots)} 张图，总结这个账号的配图模板：整体风格、有哪几种页…", None)
    seen = [(label, rel, u) for label, rel in shots if (u := _vision_uri(rel))]
    content: list[dict] = [{"type": "text", "text": prompts.VISUAL_LEARN_USER.format(
        theme=acc.theme or "（未设定）", names="、".join(source["names"]) or "（未知）", n=len(seen),
        index="\n".join(f"图 {i + 1}：{label}" for i, (label, _, _) in enumerate(seen)))}]
    content += [image_part(u) for _, _, u in seen]
    try:
        raw = await complete_json(vllm, [{"role": "system", "content": prompts.VISUAL_LEARN_SYSTEM},
                                         {"role": "user", "content": content}], temperature=0.3)
    except LLMError as e:
        raise VisualError(f"看图模型调用失败：{e}") from e
    tpl = _clean(raw, [(label, rel) for label, rel, _ in seen], acc.visual)
    acc.visual = {**tpl, "source": {**source, "images": len(seen)}, "at": utcnow().isoformat()}
    acc.updated_at = utcnow()
    s.add(acc)
    s.commit()
    emit("visual", f"配图模板好了：{len(tpl['pages'])} 种页（{'、'.join(p['type'] for p in tpl['pages'])}），以后每篇照它出图",
         {"pages": len(tpl["pages"])})
    return {"pages": [p["type"] for p in tpl["pages"]], "images": len(seen), "spec": tpl["spec"]}


async def learn_quietly(s: Session, account_id: str, emit: Emit = _noop) -> None:
    """学完对标后顺手学配图模板：看不了图就跳过，失败不影响对标结果。"""
    if get_vision_llm() is None:
        return
    try:
        await learn(s, account_id, emit=emit)
    except Exception as e:  # noqa: BLE001
        logger.warning("配图模板没学成：%s", e)
        emit("warning", f"配图模板没学成（{e}），配图先照每篇的参考帖做", None)


async def revise(s: Session, llm: LLM, acc: Account, instruction: str) -> dict:
    """按用户的话改模板（纯文字，不用看图）：样例图按页型名字沿用。
    还没有模板（没对标、也没给链接）时按用户的描述起一套：页型没有样例图，出图照文字描述做。"""
    fresh = not has_template(acc)
    if fresh:
        cur = {"spec": acc.image_style or "", "tips": [], "pages": [{"type": "封面", "desc": "", "when": "每篇第 1 张"}]}
        extra = prompts.VISUAL_NEW_NOTE.format(theme=acc.theme or "（未设定）", style=acc.image_style or "（未设定）")
    else:
        cur = {k: acc.visual.get(k) for k in ("spec", "tips")} | {
            "pages": [{k: p.get(k, "") for k in ("type", "desc", "when")} for p in pages(acc.visual)]}
        extra = ""
    try:
        raw = await complete_json(llm, [
            {"role": "system", "content": prompts.VISUAL_UPDATE_SYSTEM},
            {"role": "user", "content": prompts.VISUAL_UPDATE_USER.format(
                current=json.dumps(cur, ensure_ascii=False, indent=1), instruction=instruction.strip()[:300]) + extra},
        ], temperature=0.3)
    except LLMError as e:
        raise VisualError(str(e)) from e
    for p in raw.get("pages") or []:
        if isinstance(p, dict):
            p.pop("examples", None)
    if not isinstance(raw, dict):
        raise VisualError("模型没给出模板")
    tpl = _clean(raw, [], acc.visual)
    if fresh:
        tpl["pages"][0]["examples"] = []  # 没有样例图：_clean 补封面时不会有图，这里明确一下
    base = {} if fresh else dict(acc.visual or {})
    acc.visual = {**base, **tpl, **({"source": {"kind": "text", "names": ["按你的描述"]}} if fresh else {}),
                  "at": utcnow().isoformat()}
    acc.updated_at = utcnow()
    s.add(acc)
    s.commit()
    changed = (f"按你的描述起了一套配图模板：{len(tpl['pages'])} 种页（{'、'.join(p['type'] for p in tpl['pages'])}）" if fresh
               else str(raw.get("changed") or ""))
    return {"changed": changed[:100],
            "pages": [p["type"] for p in tpl["pages"]], "spec": tpl["spec"], **({"created": True} if fresh else {})}


def patch(s: Session, acc: Account, *, spec: str | None = None, pages_in: list[dict] | None = None,
          clear: bool = False) -> dict:
    """界面里手动改：改整体视觉、改/删页型（样例按名字沿用）、或整个清掉。"""
    if clear:
        acc.visual = {}
    else:
        v = dict(acc.visual or {})
        if spec is not None:
            v["spec"] = " ".join(spec.split())[:400]
        if pages_in is not None:
            old = {p["type"]: p for p in pages(v)}
            new = []
            for p in pages_in:
                t = " ".join(str(p.get("type") or "").split())[:12]
                if not t:
                    continue
                keep = old.get(t) or old.get(str(p.get("from") or ""), {})
                new.append({"type": t, "desc": " ".join(str(p.get("desc") or "").split())[:160],
                            "when": " ".join(str(p.get("when") or "").split())[:60],
                            "examples": [e for e in (p.get("examples") or keep.get("examples") or []) if _exists(e)][:3]})
            v["pages"] = new[:MAX_PAGES]
        if not v.get("spec") or not pages(v):
            raise VisualError("模板至少要有整体视觉和一种页型")
        v["at"] = utcnow().isoformat()
        acc.visual = v
    acc.updated_at = utcnow()
    s.add(acc)
    s.commit()
    return acc.visual


# ── 出图后自检 ──────────────────────────────────────────────────────────


def check_enabled() -> bool:
    from mediaflow import credentials

    return credentials.get("image_check") != "off"


async def check_image(vllm: LLM, data: bytes, prompt: str, spec: str, *, refs: list[str] | None = None) -> dict:
    """看一张刚出好的图：{ok, problems, fix}。refs 是出这张图时给生图模型的参考图（顺序同「参考图 1、2」），
    一起给质检看，免得把照版式模板做出来的画风当成跑偏。看不了（模型出错）当作通过，不耽误出图。"""
    from mediaflow.services.refs import uri_of

    uri = await asyncio.to_thread(uri_of, data)
    if not uri:
        return {"ok": True, "problems": [], "fix": "", "skipped": True}
    refs = [r for r in refs or [] if r]
    note = ""
    if len(refs) == 1:
        note = "第 1 张附图是要检查的图，第 2 张附图就是要求里说的「参考图」。"
    elif refs:
        note = "第 1 张附图是要检查的图；要求里的「参考图 1」「参考图 2」依次是第 2、3 张附图。"
    if refs and ("版式模板" in prompt or "照着参考图的版式" in prompt):
        note += "版式和画风以版式模板为准（模板本来就是插画/实拍等画风不算跑偏），同套已出好的图只比配色、字体、人物。"
    content: list[dict] = [{"type": "text", "text": prompts.IMAGE_CHECK_USER.format(
        prompt=prompt[:1200], spec=spec[:400], anchor_note=note)}, image_part(uri), *[image_part(r) for r in refs]]
    try:
        raw = await complete_json(vllm, [{"role": "system", "content": prompts.IMAGE_CHECK_SYSTEM},
                                         {"role": "user", "content": content}], temperature=0.1)
    except LLMError as e:
        logger.info("配图自检没做成：%s", e)
        return {"ok": True, "problems": [], "fix": "", "skipped": True}
    problems = [" ".join(str(x).split())[:80] for x in raw.get("problems") or [] if str(x).strip()][:4]
    ok = bool(raw.get("ok", not problems))
    return {"ok": ok, "problems": problems if not ok else problems[:2], "fix": "" if ok else " ".join(str(raw.get("fix") or "").split())[:200]}
