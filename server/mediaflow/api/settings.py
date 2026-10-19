"""设置：各平台搜索凭据（数据来源）、AI 配图的 Key 和模型，都可以实测一次。"""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from mediaflow import credentials
from mediaflow.config import get_settings
from mediaflow.domain.schemas import SourceStatusOut
from mediaflow.services import images
from mediaflow.sources.registry import fetch_all

router = APIRouter(prefix="/api/settings", tags=["settings"])


class CredentialOut(BaseModel):
    key: str
    platform: str
    label: str
    kind: str
    help: str
    url: str
    configured: bool
    auto_refresh: bool = False
    origin: str = Field(description="ui=界面里填的；env=来自 .env；空=没配置")


class CredentialsIn(BaseModel):
    values: dict[str, str | None] = Field(description="null 不改；空字符串清除")


class SourceSample(BaseModel):
    title: str
    url: str
    heat: str
    kind: str


class SourceTestIn(BaseModel):
    keyword: str = "秋季穿搭"


class SourceTestOut(BaseModel):
    keyword: str
    sources: list[SourceStatusOut]
    samples: dict[str, list[SourceSample]]


def _list() -> list[CredentialOut]:
    stored = credentials._load()
    s = get_settings()
    out = []
    for sp in credentials.SPECS:
        if sp.hidden:
            continue
        origin = "ui" if stored.get(sp.key) else ("env" if getattr(s, sp.key, "") else "")
        d = {k: v for k, v in sp.__dict__.items() if k != "hidden"}
        out.append(CredentialOut(**d, configured=bool(origin), origin=origin,
                                 auto_refresh=sp.key == "bilibili_cookie" and bool(stored.get("bilibili_refresh_token"))))
    return out


@router.get("/credentials", response_model=list[CredentialOut])
def list_credentials():
    return _list()


@router.put("/credentials", response_model=list[CredentialOut])
def update_credentials(body: CredentialsIn):
    values = dict(body.values)
    if values.get("bilibili_cookie") is not None:
        values["bilibili_refresh_token"] = ""  # 手动换了 Cookie，旧的刷新口令就对不上了
    credentials.update(values)
    return _list()


@router.post("/sources/test", response_model=SourceTestOut)
async def test_sources(body: SourceTestIn):
    kw = body.keyword.strip() or "秋季穿搭"
    report = await fetch_all(kw, limit=5)
    samples: dict[str, list[SourceSample]] = {}
    for it in report.items:
        lst = samples.setdefault(it.source, [])
        if len(lst) < 3:
            lst.append(SourceSample(title=it.title, url=it.url, heat=it.heat, kind=it.kind))
    return SourceTestOut(keyword=kw, sources=[SourceStatusOut(**st.__dict__) for st in report.statuses],
                         samples=samples)


class QrOut(BaseModel):
    url: str
    key: str


class QrPollOut(BaseModel):
    status: str = Field(description="waiting|scanned|expired|ok|error")
    message: str = ""


@router.post("/bilibili/qrcode", response_model=QrOut)
async def bilibili_qrcode():
    from mediaflow.sources.bili_auth import qr_generate
    return QrOut(**await qr_generate())


@router.get("/bilibili/qrcode/{key}", response_model=QrPollOut)
async def bilibili_qrcode_poll(key: str):
    from mediaflow.sources.bili_auth import qr_poll
    return QrPollOut(**await qr_poll(key))


@router.post("/bilibili/refresh", response_model=QrPollOut)
async def bilibili_refresh():
    from mediaflow.sources.bili_auth import refresh_if_needed
    res = await refresh_if_needed(force=False)
    return QrPollOut(status=res.split(":")[0], message=res.partition(":")[2])


@router.post("/xiaohongshu/qrcode", response_model=QrOut)
async def xiaohongshu_qrcode():
    from mediaflow.sources.xhs import qr_create
    return QrOut(**await qr_create())


@router.get("/xiaohongshu/qrcode/{key}", response_model=QrPollOut)
async def xiaohongshu_qrcode_poll(key: str):
    from mediaflow.sources.xhs import qr_poll
    return QrPollOut(**await qr_poll(key))


# ── AI 配图 ──────────────────────────────────────────────

class ImageModelOut(BaseModel):
    id: str
    label: str
    desc: str


class ImageSettingsOut(BaseModel):
    configured: bool
    origin: str = Field(description="ui=界面里填的；env=来自 .env；空=没配置")
    model: str
    models: list[ImageModelOut]
    use_refs: bool = Field(description="出图时参考对标账号的原图")


class ImageSettingsIn(BaseModel):
    api_key: str | None = Field(default=None, description="null 不改；空字符串清除")
    model: str | None = None
    use_refs: bool | None = None


class ImageTestOut(BaseModel):
    ok: bool
    model: str
    seconds: float
    url: str = ""
    error: str = ""


def _image_out() -> ImageSettingsOut:
    stored = credentials._load()
    origin = "ui" if stored.get("image_api_key") else ("env" if get_settings().image_api_key else "")
    return ImageSettingsOut(configured=bool(origin), origin=origin, model=images.image_model(), use_refs=images.use_refs(),
                            models=[ImageModelOut(id=m.id, label=m.label, desc=m.desc) for m in images.MODELS])


@router.get("/image", response_model=ImageSettingsOut)
def get_image_settings():
    return _image_out()


@router.put("/image", response_model=ImageSettingsOut)
def update_image_settings(body: ImageSettingsIn):
    if body.model is not None and body.model and body.model not in {m.id for m in images.MODELS}:
        raise HTTPException(400, "不支持这个配图模型")
    credentials.update({"image_api_key": body.api_key, "image_model": body.model,
                        "image_refs": None if body.use_refs is None else ("" if body.use_refs else "off")})
    return _image_out()


@router.post("/image/test", response_model=ImageTestOut)
async def test_image(body: ImageSettingsIn):
    """用一句固定的封面描述实际出一张图（会消耗一次生图额度），确认 Key 和模型能用、看看效果。"""
    model = body.model or images.image_model()
    t = time.monotonic()
    try:
        provider = images.GrsaiProvider(model=model, key=(body.api_key or "").strip() or None, fallback=False)
        data = await provider.generate(TEST_PROMPT)
    except images.ImageError as e:
        return ImageTestOut(ok=False, model=model, seconds=round(time.monotonic() - t, 1), error=str(e))
    d = get_settings().images_dir / "_test"
    d.mkdir(parents=True, exist_ok=True)
    for old in sorted(d.glob("*.png"))[:-5]:  # 只留最近几张
        old.unlink(missing_ok=True)
    name = f"{int(time.time())}-{model}.png"
    (d / name).write_bytes(data)
    return ImageTestOut(ok=True, model=model, seconds=round(time.monotonic() - t, 1), url=f"/files/images/_test/{name}")


TEST_PROMPT = ("小红书图文笔记封面，竖版 3:4。明亮的窗边书桌，一位二十多岁的中国女生半身近景，笑着举起一本手账，"
               "桌上有拿铁和绿植，自然窗光，手机实拍质感。画面上方大号粗体中文标题「试试AI配图」，深色字配浅色背景，清晰醒目。"
               "不要水印、不要品牌 logo。")
