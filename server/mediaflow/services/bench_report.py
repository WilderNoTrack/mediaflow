"""对标报告：把拆解结果和合成方案整理成一份 Markdown，页面上只放三行摘要，完整内容看/下载这份报告。

报告从库里现有数据拼出来，不再调模型，所以随时打开都和当前方案一致。
"""

from __future__ import annotations

from typing import Any

from mediaflow.domain.models import Account, Benchmark

FIELD_LABEL = {"theme": "账号主题", "audience": "目标受众", "content_style": "文案风格",
               "image_style": "配图风格", "topic_type": "选题方向", "keywords": "搜索关键词"}


def _s(v: Any) -> str:
    return " ".join(str(v if v is not None else "").replace("**", "").split())


def _list(v: Any) -> list:
    return v if isinstance(v, list) else []


def _num(v: Any) -> str:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return _s(v)
    return f"{n / 10000:.1f}万" if n >= 10000 else f"{int(n)}"


def creator_stats(b: Benchmark) -> str:
    i = b.creator_info or {}
    parts = [i.get("fans") and f"{_s(i['fans'])} 粉", i.get("median_likes") and f"点赞中位数 {_num(i['median_likes'])}",
             i.get("hit_rate") is not None and f"爆款率 {round(float(i['hit_rate']) * 100)}%",
             i.get("per_week") and f"每周约 {i['per_week']} 篇", i.get("posts_read") and f"读了 {i['posts_read']} 篇"]
    return " · ".join(p for p in parts if p)


def markdown(acc: Account, benches: list[Benchmark]) -> str:
    plan = acc.bench_plan or {}
    applied = plan.get("applied") or {}
    names = "、".join(b.creator_name for b in benches) or "（还没有）"
    out = [f"# 对标报告：{acc.name}", "",
           f"> 主题：{_s(plan.get('theme') or acc.theme)}　·　对标：{names}"
           + (f"　·　更新于 {str(plan['updated_at'])[:10]}" if plan.get("updated_at") else ""), ""]

    if plan.get("summary"):
        out += ["## 一句话", "", _s(plan["summary"]), ""]

    fit = _list(plan.get("fit"))
    if fit:
        out += ["## ⚠ 跨领域提醒", ""]
        for x in fit:
            dom = f"主要做{x['domain']}，" if x.get("domain") else ""
            out.append(f"- **{_s(x.get('creator'))}**：{dom}和你的「{_s(plan.get('theme') or acc.theme)}」不是一个领域。"
                       + (f"{note}。" if (note := _s(x.get('note')).rstrip('。；;，, ')) else ""))
        out.append("")

    prof = applied.get("profile") or {}
    rules = _list(applied.get("rules"))
    topics = _list(applied.get("topics"))
    if prof or rules or topics:
        out += ["## 已经帮你改好的", ""]
        if prof:
            out += ["**账号定位**", ""]
            out += [f"- {FIELD_LABEL.get(k, k)}：{'、'.join(map(_s, v)) if isinstance(v, list) else _s(v)}" for k, v in prof.items()]
            out.append("")
        if rules:
            out += ["**写法规则**（每篇都会遵守）", ""] + [f"{i + 1}. {_s(r)}" for i, r in enumerate(rules)] + [""]
        if topics:
            out += [f"**复刻选题**（{len(topics)} 个，已放进选题库）", ""] + [f"- {_s(t)}" for t in topics] + [""]

    steps = _list(plan.get("steps"))
    if steps:
        out += ["## 起号建议", ""] + [f"{i + 1}. {_s(x)}" for i, x in enumerate(steps)] + [""]

    borrow = [x for x in _list(plan.get("borrow")) if isinstance(x, dict)]
    if borrow:
        out += ["## 每一块学谁", ""] + [f"- **{_s(x.get('aspect'))}**（学 {_s(x.get('from'))}）：{_s(x.get('how'))}" for x in borrow] + [""]

    pillars = [x for x in _list(plan.get("pillars")) if isinstance(x, dict)]
    if pillars:
        out += ["## 你的内容栏目", ""]
        out += [f"- **{_s(x.get('name'))}**" + (f"（{_s(x.get('share'))}）" if x.get("share") else "")
                + (f"：学 {_s(x.get('from'))}" if x.get("from") else "") for x in pillars] + [""]

    for b in benches:
        out += _creator(b)
    return "\n".join(out).rstrip() + "\n"


def _creator(b: Benchmark) -> list[str]:
    p = b.playbook or {}
    out = [f"## 拆解：{b.creator_name}", ""]
    meta = creator_stats(b)
    if p.get("domain"):
        meta = f"领域：{_s(p['domain'])}" + (f" · {meta}" if meta else "")
    if meta:
        out += [f"> {meta}", ""]
    if b.creator_url:
        out += [f"主页：[{b.creator_name}]({b.creator_url})", ""]

    def sec(title: str, body: Any) -> None:
        if isinstance(body, list):
            items = [_s(x) for x in body if _s(x)]
            if items:
                out.extend([f"### {title}", "", *[f"- {x}" for x in items], ""])
        elif _s(body):
            out.extend([f"### {title}", "", str(body).replace("**", "").strip(), ""])

    sec("靠什么火", p.get("summary"))
    sec("人设", p.get("persona"))
    sec("受众", p.get("audience"))
    pillars = [x for x in _list(p.get("pillars")) if isinstance(x, dict)]
    if pillars:
        out += ["### 内容栏目", ""]
        for x in pillars:
            ex = "、".join(f"《{_s(e)}》" for e in _list(x.get("examples"))[:3])
            out.append(f"- **{_s(x.get('name'))}**" + (f"（{_s(x.get('share'))}）" if x.get("share") else "")
                       + f"：{_s(x.get('desc'))}" + (f" 例：{ex}" if ex else ""))
        out.append("")
    formulas = [x for x in _list(p.get("title_formulas")) if isinstance(x, dict)]
    if formulas:
        out += ["### 标题公式", ""] + [f"- **{_s(f.get('formula'))}**" + (f" —— 例：{_s(f.get('example'))}" if f.get("example") else "")
                                      for f in formulas] + [""]
    sec("开头钩子", _list(p.get("hooks")))
    sec("正文结构", p.get("structure"))
    sec("封面与配图", p.get("visual"))
    sec("标签打法", p.get("tags"))
    sec("更新节奏", p.get("cadence"))
    sec("评论区在关心", _list(p.get("audience_needs")))
    sec("爆款和普通作品差在哪", p.get("hit_pattern"))
    sec("这些别照搬", _list(p.get("not_copyable")))

    hits, seen = [], set()
    for x in b.samples or []:
        t = _s(x.get("title"))
        if not t or t in seen:
            continue
        seen.add(t)
        stat = " · ".join(v for v in (x.get("likes") and f"赞 {_s(x['likes'])}", x.get("date") and _s(x["date"])) if v)
        hits.append(f"- [{t}]({x['url']})" if x.get("url") else f"- {t}")
        if stat:
            hits[-1] += f"（{stat}）"
    if hits:
        out += [f"### TA 的爆款（{len(hits)}）", "", *hits, ""]
    return out
