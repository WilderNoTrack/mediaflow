"""样板帖：账号选定的一篇爆款，整个号的图都照它一个风格。

起号时找几篇同领域的爆款给用户挑，照着写出第一篇；用户觉得这套图对味，就把那篇爆款定为样板。
定了以后每篇的配图都一张对一张照这篇爆款的原图做（画风、版式、每张的做法、字多字少），整个号一个风格；
文字不用那么严：只学它为什么火（选题角度、钩子、信息密度），按账号定位和本篇选题自由写。
用户这篇另外指定了要照的爆款（「照这篇写」），这篇就照指定的那篇；选题来源的原帖只当内容参考。

老数据里样板帖是一篇自己的草稿（draft_id）：照旧能用，配图照那篇草稿的图做。
"""

from __future__ import annotations

from typing import Any

from sqlmodel import Session, col, select

from mediaflow.config import get_settings
from mediaflow.domain.models import Account, Draft, DraftImage, ImageStatus, utcnow

CREATOR = "你的样板帖"


POST_KEYS = ("title", "url", "creator", "likes", "content", "tags", "local", "look", "cover")


def _post(acc: Account | None) -> dict | None:
    """样板是一篇爆款时返回那篇（含缓存的原图和读图结果）。"""
    p = (acc.exemplar or {}).get("post") if acc else None
    return p if isinstance(p, dict) and p.get("title") and p.get("local") else None


def get(s: Session, acc: Account | None) -> Draft | None:
    if _post(acc) is not None:
        return None
    did = str((acc.exemplar or {}).get("draft_id") or "") if acc else ""
    d = s.get(Draft, did) if did else None
    return d if d is not None and d.account_id == acc.id else None


def _images(s: Session, draft_id: str) -> list[DraftImage]:
    return list(s.exec(select(DraftImage).where(DraftImage.draft_id == draft_id).order_by(col(DraftImage.idx))).all())


def info(s: Session, acc: Account) -> dict:
    """给前端和小媒看的概况；样板帖被删了就当没有。"""
    p = _post(acc)
    at = (acc.exemplar or {}).get("at", "")
    if p is not None:
        return {"kind": "post", "title": p["title"], "url": p.get("url", ""), "creator": p.get("creator", ""),
                "likes": p.get("likes", ""), "images": len(p["local"]), "cover": p["local"][0], "at": at,
                "draft_id": str((acc.exemplar or {}).get("from_draft") or "")}
    d = get(s, acc)
    if d is None:
        return {}
    imgs = [i for i in _images(s, d.id) if i.status == ImageStatus.done and i.path]
    return {"kind": "draft", "draft_id": d.id, "title": d.title, "at": at,
            "images": len(imgs), "cover": imgs[0].path if imgs else ""}


def is_post(ref: dict | None) -> bool:
    """这篇参考是不是别人的爆款（有缓存好的原图），能当样板。"""
    ref = ref or {}
    return bool(ref.get("title") and ref.get("local")) and ref.get("source") != "exemplar"


def set_post(s: Session, acc: Account, ref: dict, *, from_draft: str = "") -> dict:
    """把一篇爆款定为样板：之后每篇的配图都照它的原图做。"""
    if not is_post(ref):
        raise ValueError("这篇没拿到原图，当不了样板；换一篇图文笔记")
    post = {k: ref[k] for k in POST_KEYS if ref.get(k)}
    acc.exemplar = {"post": post, "title": post["title"], "at": utcnow().isoformat(),
                    **({"from_draft": from_draft} if from_draft else {})}
    acc.updated_at = utcnow()
    s.add(acc)
    s.commit()
    return info(s, acc)


async def set_from_url(s: Session, acc: Account, url: str) -> dict:
    """贴一篇爆款链接定为样板：读出来、缓存原图、看懂每张图是怎么做的。链接用不了抛 refpost.RefError。"""
    from mediaflow.services import refpost, visual

    ref = await refpost.from_url(url)
    if visual.get_vision_llm() is not None and ref.get("local"):
        try:
            look = await visual.read_post(ref)
        except Exception:  # noqa: BLE001 - 读图失败不影响定样板，写稿时再读
            look = None
        if look:
            ref["look"] = look
    return set_post(s, acc, ref)


def set_(s: Session, acc: Account, draft: Draft) -> dict:
    """草稿页「定为样板」：这篇是照着某篇爆款做的，样板就是那篇爆款（图照原图做最像）；
    这篇没照爆款写（或原图没拿到），才把这篇草稿自己当样板。"""
    if draft.account_id != acc.id:
        raise LookupError("这篇草稿不属于这个账号")
    if is_post(draft.reference):
        return set_post(s, acc, draft.reference, from_draft=draft.id)
    acc.exemplar = {"draft_id": draft.id, "title": draft.title, "at": utcnow().isoformat()}
    acc.updated_at = utcnow()
    s.add(acc)
    s.commit()
    return info(s, acc)


def clear(s: Session, acc: Account) -> None:
    acc.exemplar = {}
    acc.updated_at = utcnow()
    s.add(acc)
    s.commit()


def forget_draft(s: Session, draft: Draft) -> None:
    """删草稿时：如果它是样板帖，账号就没有样板帖了。"""
    acc = s.get(Account, draft.account_id)
    if acc is not None and _post(acc) is None and (acc.exemplar or {}).get("draft_id") == draft.id:
        acc.exemplar = {}
        s.add(acc)


def _mold(img: DraftImage) -> str:
    """这张当版式模板用哪张图：AI 画面 + 代码排字的用没排字的底图（不然 AI 会跟着画字），其余用成图。"""
    from mediaflow.services.refs import cache_file

    images_dir = get_settings().images_dir
    base = str((img.source or {}).get("base") or "")
    if img.made_by == "ai_text" and base and (images_dir / base).exists():
        return cache_file(base)
    return cache_file(img.path) if img.path else ""


def as_reference(s: Session, acc: Account | None) -> dict[str, Any] | None:
    """样板帖 → 写稿用的主参考帖。样板是爆款：就是那篇（source=exemplar_post，配图照原图、照读图结果挑做法）；
    样板是自己的草稿：和 refpost 的格式一样，多了 plan（每张图的做法、版式、配色）。没有样板帖返回 None。"""
    p = _post(acc)
    if p is not None:
        return {**p, "source": "exemplar_post", "why": "账号的样板爆款：每篇配图都照它一个风格"}
    d = get(s, acc)
    if d is None:
        return None
    local, plan = _image_parts(s, d)
    return {"title": d.title, "content": d.body, "tags": list(d.tags or []), "creator": CREATOR,
            "source": "exemplar", "why": "账号的样板帖：后面每篇都照它的写法和配图来", "draft_id": d.id,
            "local": local, "plan": plan, "image_spec": d.image_spec or ""}


def refresh(s: Session, ref: dict[str, Any]) -> dict[str, Any]:
    """出图前按样板帖现在的图更新参考：写这篇时样板的图还没出好、或者后来又改过图，都照最新的来。
    样板那篇已经删了就保持原样。"""
    if ref.get("source") != "exemplar" or not ref.get("draft_id"):
        return ref
    d = s.get(Draft, str(ref["draft_id"]))
    if d is None:
        return ref
    local, plan = _image_parts(s, d)
    if not local:
        return ref
    return {**ref, "local": local, "plan": plan, "image_spec": d.image_spec or ref.get("image_spec") or ""}


def _src_look(pages: list[dict], local: list[str], idx: int) -> str:
    """样板这张当初照的是原帖哪张、那张是什么做法。"""
    from mediaflow.services.images import mold_slot
    from mediaflow.services.visual import look_line

    if not pages or not local:
        return ""
    k = mold_slot(local, idx)
    return look_line(pages[k]) if k < len(pages) else ""


def _image_parts(s: Session, d: Draft) -> tuple[list[str], list[dict]]:
    # 样板这篇当初照着别人的帖子做过：每张原型是什么做法（漫画 / 拼图 / 实拍…）也带上，后面照样板做时更像
    src = d.reference or {}
    src_look = [p for p in ((src.get("look") or {}).get("pages") or []) if isinstance(p, dict)] \
        if src.get("source") != "exemplar" else []
    src_local = src.get("local") or []
    local, plan = [], []
    for img in _images(s, d.id):
        if img.status != ImageStatus.done or not img.path:
            continue
        mold = _mold(img)
        if not mold:
            continue
        lay = img.layout or {}
        local.append(mold)
        plan.append({k: v for k, v in {
            "made_by": img.made_by or "ai", "kind": lay.get("kind", ""), "palette": lay.get("palette", ""),
            "position": lay.get("position", ""), "page_type": img.page_type, "prompt": img.prompt[:160],
            "look": _src_look(src_look, src_local, img.idx),
        }.items() if v})
    return local, plan
