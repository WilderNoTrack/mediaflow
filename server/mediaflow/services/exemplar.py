"""样板帖：用户亲手打磨定稿的一篇。

起号时先陪用户把第一篇打磨好（照着找来的对标帖子写、再按用户的话改），用户满意就定为样板帖。
定了以后每篇都以它为主参考：文案的标题写法、开头、结构、篇幅、语气照它；配图一张对一张照它的做法、版式和配色。
对标账号的爆款、用户另给的链接只当文案参考（选题角度、信息点），不再决定写法和配图。
"""

from __future__ import annotations

from typing import Any

from sqlmodel import Session, col, select

from mediaflow.config import get_settings
from mediaflow.domain.models import Account, Draft, DraftImage, ImageStatus, utcnow

CREATOR = "你的样板帖"


def get(s: Session, acc: Account | None) -> Draft | None:
    did = str((acc.exemplar or {}).get("draft_id") or "") if acc else ""
    d = s.get(Draft, did) if did else None
    return d if d is not None and d.account_id == acc.id else None


def _images(s: Session, draft_id: str) -> list[DraftImage]:
    return list(s.exec(select(DraftImage).where(DraftImage.draft_id == draft_id).order_by(col(DraftImage.idx))).all())


def info(s: Session, acc: Account) -> dict:
    """给前端和小媒看的概况；样板帖被删了就当没有。"""
    d = get(s, acc)
    if d is None:
        return {}
    imgs = [i for i in _images(s, d.id) if i.status == ImageStatus.done and i.path]
    return {"draft_id": d.id, "title": d.title, "at": (acc.exemplar or {}).get("at", ""),
            "images": len(imgs), "cover": imgs[0].path if imgs else ""}


def set_(s: Session, acc: Account, draft: Draft) -> dict:
    if draft.account_id != acc.id:
        raise LookupError("这篇草稿不属于这个账号")
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
    if acc is not None and (acc.exemplar or {}).get("draft_id") == draft.id:
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
    """样板帖 → 写稿用的主参考帖（和 refpost 的格式一样，多了 plan：每张图的做法、版式、配色）。没有样板帖返回 None。"""
    d = get(s, acc)
    if d is None:
        return None
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
        }.items() if v})
    return {"title": d.title, "content": d.body, "tags": list(d.tags or []), "creator": CREATOR,
            "source": "exemplar", "why": "账号的样板帖：后面每篇都照它的写法和配图来", "draft_id": d.id,
            "local": local, "plan": plan, "image_spec": d.image_spec or ""}
