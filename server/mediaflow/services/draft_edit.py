"""改草稿的配图：改描述、加一张、删一张、调顺序、照原描述重出。页面和小媒（对话里说「第二张换成…」）共用这一套。

编号一律按改之前的顺序（用户/小媒看到的「第几张」），一次可以给好几步；改过描述的、新加的、要重出的标成待出图，
其余已经出好的保持不动，再出图时沿用这一套的统一视觉规范、带上已出的图当风格参照（见 images.py）。
"""

from __future__ import annotations

from typing import Any

from sqlmodel import Session, col, select

from mediaflow.domain.models import Draft, DraftImage, ImageStatus, Job, JobKind, JobStatus, utcnow

MAX_IMAGES = 9


class EditError(ValueError):
    """改不了（编号不对、删光了、超过 9 张、正在出图），信息直接给用户/小媒看。"""


def images_of(session: Session, draft_id: str) -> list[DraftImage]:
    return list(session.exec(select(DraftImage).where(DraftImage.draft_id == draft_id).order_by(col(DraftImage.idx))).all())


def images_busy(session: Session, draft_id: str) -> bool:
    jobs = session.exec(select(Job).where(Job.kind == JobKind.generate_images,
                                          col(Job.status).in_([JobStatus.queued, JobStatus.running]))).all()
    return any(j.payload.get("draft_id") == draft_id for j in jobs)


def _no(op: dict, key: str, n: int, *, allow_zero: bool = False) -> int:
    try:
        v = int(op.get(key))
    except (TypeError, ValueError):
        raise EditError(f"{op.get('op')} 要给 {key}（第几张）") from None
    if not (0 if allow_zero else 1) <= v <= n:
        raise EditError(f"没有第 {v} 张（现在一共 {n} 张）")
    return v


def apply_ops(session: Session, draft: Draft, ops: list[dict[str, Any]]) -> dict:
    """按顺序执行 ops，返回 {"changed": [改后的第几张…], "retexted": [直接改了字的第几张…], "removed": n, "total": n}。
    op: update(no, description) / add(after, description, mode；after=0 放最前，不给就放最后) / remove(no) / move(no, to) / redo(no)
    / mode(no, mode[, description])：换做法重出（ai / ai_text / card / photo，空 = 跟账号设定）
    / text(no, layout)：直接改代码排上去的字（标题、要点…），马上重排，不重新生图。"""
    from mediaflow.services import images as images_mod
    if images_busy(session, draft.id):
        raise EditError("这篇正在出图，等这一轮出完再改")
    orig = images_of(session, draft.id)
    n = len(orig)
    removed: set[str] = set()
    changed: set[str] = set()
    adds: list[tuple[int, DraftImage]] = []
    moves: list[tuple[DraftImage, int]] = []
    texts: list[tuple[DraftImage, dict]] = []
    for op in ops:
        kind = str(op.get("op") or "")
        desc = " ".join(str(op.get("description") or "").split())
        mode = str(op.get("mode") or "").strip().lower()
        if mode == "auto":
            mode = ""
        if mode and mode not in images_mod.IMAGE_MODES:
            raise EditError(f"不认识的做法 {mode}（只能 ai / ai_text / card / photo）")
        if kind in ("update", "redo", "remove", "move", "mode", "text"):
            img = orig[_no(op, "no", n) - 1]
            if kind == "update":
                if not desc:
                    raise EditError("update 要给新的 description")
                img.prompt = desc[:500]
                changed.add(img.id)
            elif kind == "redo":
                changed.add(img.id)
            elif kind == "mode":
                img.mode = mode
                if desc:
                    img.prompt = desc[:500]
                changed.add(img.id)
            elif kind == "text":
                lay = op.get("layout") if isinstance(op.get("layout"), dict) else {
                    k: op[k] for k in images_mod.LAYOUT_KEYS if op.get(k) is not None}
                if not lay:
                    raise EditError("text 要给改后的字（layout：title / subtitle / items …）")
                texts.append((img, lay))
            elif kind == "remove":
                removed.add(img.id)
            else:
                moves.append((img, int(op.get("to") or 1)))
        elif kind == "add":
            if not desc:
                raise EditError("add 要给这张的 description")
            after = _no(op, "after", n, allow_zero=True) if op.get("after") is not None else n
            new = DraftImage(draft_id=draft.id, idx=-1, prompt=desc[:500], mode=mode)
            adds.append((after, new))
            changed.add(new.id)
        else:
            raise EditError(f"不认识的操作 {kind}（只能 update/add/remove/move/redo/mode/text）")

    order = [i for i in orig if i.id not in removed]

    def pos_of(img: DraftImage) -> int:
        return next((k for k, x in enumerate(order) if x.id == img.id), -1)

    front, after_count = 0, {}
    for after, new in adds:  # 同一个位置加好几张，按给的先后排
        if after == 0:
            order.insert(front, new)
            front += 1
            continue
        anchor = orig[after - 1]
        k = pos_of(anchor)
        if k < 0:
            order.append(new)
            continue
        order.insert(k + 1 + after_count.get(anchor.id, 0), new)
        after_count[anchor.id] = after_count.get(anchor.id, 0) + 1
    for img, to in moves:
        k = pos_of(img)
        if k >= 0:
            order.pop(k)
            order.insert(max(0, min(len(order), to - 1)), img)
    if not order:
        raise EditError("至少要留一张图")
    if len(order) > MAX_IMAGES:
        raise EditError(f"小红书一篇最多 {MAX_IMAGES} 张图")

    for img, lay in texts:  # 先排好再动数据库：排不了（AI 画的字、底图没了）直接报错，什么都不改
        if img.id in removed or img.id in changed:
            continue
        try:
            images_mod.rerender(img, lay)
        except (ValueError, RuntimeError) as e:  # LayoutError：AI 直接画的字、底图没了、没有中文字体
            session.rollback()
            raise EditError(str(e)) from e
    for img in orig:
        if img.id in removed:
            session.delete(img)
    session.flush()
    for k, img in enumerate(order):
        img.idx = k
        if img.id in changed:
            img.status, img.error, img.ref_path = ImageStatus.pending, "", ""
        img.updated_at = utcnow()
        session.add(img)
    draft.updated_at = utcnow()
    session.add(draft)
    session.commit()
    texted = {i.id for i, _ in texts if i.id not in changed and i.id not in removed}
    return {"changed": [k + 1 for k, i in enumerate(order) if i.id in changed],
            "retexted": [k + 1 for k, i in enumerate(order) if i.id in texted], "removed": len(removed), "total": len(order)}


def summary(session: Session, draft: Draft, *, body_chars: int = 1200) -> dict:
    """给小媒看的草稿概况：文案、每张图的描述和状态、参考了哪些帖子。"""
    ref = draft.reference or {}
    imgs = images_of(session, draft.id)
    return {
        "id": draft.id, "title": draft.title, "body": draft.body[:body_chars] + ("…" if len(draft.body) > body_chars else ""),
        "tags": draft.tags, "score": draft.score, "status": draft.status.value,
        "images": [_img_summary(i) for i in imgs],
        "image_style": draft.image_spec[:300],
        "reference": {"title": ref.get("title", ""), "extra": [x.get("title", "") for x in ref.get("extra") or []]} if ref else {},
        "busy": images_busy(session, draft.id),
    }


def _img_summary(i: DraftImage) -> dict:
    out: dict[str, Any] = {"no": i.idx + 1, "description": i.prompt, "status": i.status.value}
    if i.page_type:
        out["page_type"] = i.page_type
    if i.made_by:
        out["made_by"] = i.made_by
    if i.mode:
        out["mode"] = i.mode
    lay = i.layout or {}
    if i.made_by in ("card", "photo", "ai_text") and lay:
        out["text"] = {k: lay[k] for k in ("kind", "title", "subtitle", "items", "left", "right", "tag") if lay.get(k)}
    src = i.source or {}
    if src.get("site"):
        out["photo_from"] = src["site"]
    if i.error:
        out["error"] = i.error[:80]
    return out
