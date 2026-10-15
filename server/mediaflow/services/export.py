"""导出：文案 + 配图打包成 zip，方便手动发到小红书。"""

from __future__ import annotations

import io
import zipfile

from sqlmodel import Session, col, select

from mediaflow.config import get_settings
from mediaflow.domain.models import Draft, DraftImage, ImageStatus


def post_text(d: Draft) -> str:
    tags = " ".join(f"#{t}" for t in d.tags)
    return f"{d.title}\n\n{d.body}\n\n{tags}".strip() + "\n"


def build_zip(session: Session, draft_id: str) -> tuple[bytes, str]:
    d = session.get(Draft, draft_id)
    if d is None:
        raise LookupError("草稿不存在")
    imgs = session.exec(
        select(DraftImage).where(DraftImage.draft_id == draft_id, DraftImage.status == ImageStatus.done)
        .order_by(col(DraftImage.idx))
    ).all()
    buf = io.BytesIO()
    root = get_settings().images_dir
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("文案.txt", post_text(d))
        for n, img in enumerate(imgs, start=1):
            p = root / img.path
            if p.exists():
                z.write(p, f"{n:02d}{p.suffix}")
    safe = "".join(ch for ch in d.title if ch not in '\\/:*?"<>|').strip() or "draft"
    return buf.getvalue(), f"{safe[:30]}.zip"
