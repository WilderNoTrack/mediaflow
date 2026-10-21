"""设置：各平台搜索凭据（数据来源）、AI 配图的 Key 和模型，都可以实测一次。"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from mediaflow import credentials
from mediaflow.api.deps import require_admin
from mediaflow.config import get_settings
from mediaflow.domain.schemas import SourceStatusOut
from mediaflow.services import images
from mediaflow.sources.registry import fetch_all

router = APIRouter(prefix="/api/settings", tags=["settings"])
ADMIN = Depends(require_admin)  # Key、平台账号是全站共用的，只有管理员能改


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


@router.post("/sources/test", response_model=SourceTestOut, dependencies=[ADMIN])
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


@router.post("/bilibili/qrcode", response_model=QrOut, dependencies=[ADMIN])
async def bilibili_qrcode():
    from mediaflow.sources.bili_auth import qr_generate
    return QrOut(**await qr_generate())


@router.get("/bilibili/qrcode/{key}", response_model=QrPollOut, dependencies=[ADMIN])
async def bilibili_qrcode_poll(key: str):
    from mediaflow.sources.bili_auth import qr_poll
    return QrPollOut(**await qr_poll(key))


@router.post("/bilibili/refresh", response_model=QrPollOut, dependencies=[ADMIN])
async def bilibili_refresh():
    from mediaflow.sources.bili_auth import refresh_if_needed
    res = await refresh_if_needed(force=False)
    return QrPollOut(status=res.split(":")[0], message=res.partition(":")[2])


@router.post("/xiaohongshu/qrcode", response_model=QrOut, dependencies=[ADMIN])
async def xiaohongshu_qrcode():
    from mediaflow.sources.xhs import qr_create
    return QrOut(**await qr_create())


@router.get("/xiaohongshu/qrcode/{key}", response_model=QrPollOut, dependencies=[ADMIN])
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
    use_refs: bool = Field(description="出图时照着参考帖的原图做版式")
    check: bool = Field(True, description="出图后看图自检（有错字等问题自动重出一次）")
    vision: bool = Field(False, description="现在能不能看图（自检、学配图模板要用）")
    next_configured: bool = Field(False, description="openai-next 的 Key 配了没（配了优先用）")
    next_origin: str = ""
    next_exhausted_at: str = Field("", description="openai-next 额度用完的时间；空=没用完。用完后几个小时内直接走 grsai")
    channel: str = Field("", description="现在先用哪条：next / grsai / 空")


class ImageSettingsIn(BaseModel):
    api_key: str | None = Field(default=None, description="grsai 的 Key。null 不改；空字符串清除")
    next_api_key: str | None = Field(default=None, description="openai-next 的 Key。null 不改；空字符串清除")
    model: str | None = None
    use_refs: bool | None = None
    check: bool | None = None


class ImageTestIn(BaseModel):
    channel: str | None = Field(default=None, description="next / grsai；不填就用现在先用的那条")
    api_key: str | None = Field(default=None, description="试一个还没保存的 Key（对应 channel）")
    model: str | None = None


class LlmSettingsOut(BaseModel):
    configured: bool = Field(description="能不能写稿聊天（两条里配了任意一条）")
    origin: str = Field(description="DeepSeek 官方 Key：ui=界面里填的，env=环境变量，空=没配")
    deepseek_configured: bool = False
    next_configured: bool = Field(False, description="openai-next 的 Key 配了没（和配图共用一个 Key）")
    next_origin: str = ""
    next_model: str = Field("", description="openai-next 上调的 DeepSeek 模型名")
    channel: str = Field("auto", description="auto=openai-next 优先、出错换官方；next=只用 openai-next；deepseek=只用官方")
    order: list[str] = Field(default_factory=list, description="现在实际按这个顺序走")
    next_paused: bool = Field(False, description="openai-next 刚出过错，这一阵先走官方")


class LlmSettingsIn(BaseModel):
    api_key: str | None = Field(default=None, max_length=200, description="DeepSeek 官方 Key。null 不改；空字符串清除")
    next_api_key: str | None = Field(default=None, max_length=300, description="openai-next 的 Key（和配图共用）。null 不改；空字符串清除")
    next_model: str | None = Field(default=None, max_length=100, description="openai-next 上的模型名。null 不改；空字符串恢复默认")
    channel: str | None = Field(default=None, description="auto / next / deepseek")


class LlmTestIn(BaseModel):
    channel: str = Field("deepseek", description="next / deepseek")
    api_key: str | None = Field(default=None, max_length=300, description="试一个还没保存的 Key；不填用已保存的")
    model: str | None = Field(default=None, max_length=100)


class LlmTestOut(BaseModel):
    ok: bool
    seconds: float
    error: str = ""


def _origin(key: str) -> str:
    return "ui" if credentials._load().get(key) else ("env" if getattr(get_settings(), key, "") else "")


def _llm_out() -> LlmSettingsOut:
    from mediaflow.llm import client as c

    origin, next_origin = _origin("deepseek_api_key"), _origin("image_next_api_key")
    return LlmSettingsOut(configured=bool(origin or next_origin), origin=origin, deepseek_configured=bool(origin),
                          next_configured=bool(next_origin), next_origin=next_origin, next_model=c.next_llm_model(),
                          channel=c.llm_channel_pref(), order=c.llm_channels(), next_paused=c.next_paused())


@router.get("/llm", response_model=LlmSettingsOut)
def get_llm_settings():
    return _llm_out()


@router.put("/llm", response_model=LlmSettingsOut, dependencies=[ADMIN])
async def update_llm_settings(body: LlmSettingsIn):
    """填了新 Key 先实际问一句，能用才保存（填错了当场就知道）；空字符串清除。"""
    from mediaflow.llm.client import reset_next_pause

    if body.channel is not None and body.channel not in ("auto", "next", "deepseek"):
        raise HTTPException(400, "channel 只能是 auto / next / deepseek")
    key = (body.api_key or "").strip()
    if key:
        r = await _try_llm("deepseek", key)
        if not r.ok:
            raise HTTPException(400, r.error)
    nkey, nmodel = (body.next_api_key or "").strip(), (body.next_model or "").strip()
    if nkey or nmodel:
        r = await _try_llm("next", nkey or None, nmodel or None)
        if not r.ok:
            raise HTTPException(400, r.error)
    credentials.update({"deepseek_api_key": None if body.api_key is None else key,
                        "image_next_api_key": None if body.next_api_key is None else nkey,
                        "llm_next_model": None if body.next_model is None else nmodel,
                        "llm_channel": None if body.channel is None else ("" if body.channel == "auto" else body.channel)})
    if nkey or nmodel:
        reset_next_pause()
    return _llm_out()


@router.post("/llm/test", response_model=LlmTestOut, dependencies=[ADMIN])
async def test_llm(body: LlmTestIn):
    return await _try_llm(body.channel, (body.api_key or "").strip() or None, (body.model or "").strip() or None)


async def _try_llm(channel: str, key: str | None, model: str | None = None) -> LlmTestOut:
    from mediaflow.llm.client import LLMError, make_channel

    t = time.monotonic()
    nxt = channel == "next"
    try:
        await make_channel("next" if nxt else "deepseek", api_key=key, model=model).complete(
            [{"role": "user", "content": "回复「好」"}], temperature=0)
    except LLMError as e:
        msg = str(e)
        low = msg.lower()
        if "401" in msg or "auth" in low or "invalid" in low and "model" not in low:
            msg = "Key 不对：去后台重新复制一遍" + ("（openai-next 的 sk- 开头那串）" if nxt else "（以 sk- 开头）")
        elif "402" in msg or "balance" in low or "quota" in low or "额度" in msg or "余额" in msg:
            msg = ("openai-next 额度用完了，先去充值" if nxt else "DeepSeek 账户余额不足，先去充值")
        elif nxt and ("model" in low or "404" in msg or "not found" in low or "不存在" in msg):
            msg = f"openai-next 上没有这个模型（{model or '默认模型'}），去 openai-next 的模型列表复制准确的名字：{msg[:160]}"
        elif nxt and model and ("503" in msg or "500" in msg):
            msg = f"openai-next 调不通这个模型（{model}），多半是模型名不对，去 openai-next 的模型列表复制准确的名字"
        return LlmTestOut(ok=False, seconds=round(time.monotonic() - t, 1), error=msg)
    except Exception as e:  # noqa: BLE001 - 比如没配 Key
        return LlmTestOut(ok=False, seconds=round(time.monotonic() - t, 1), error=str(e) or "还没填 Key")
    return LlmTestOut(ok=True, seconds=round(time.monotonic() - t, 1))


class ImageTestOut(BaseModel):
    ok: bool
    model: str
    channel: str = ""
    seconds: float
    url: str = ""
    error: str = ""


def _image_out() -> ImageSettingsOut:
    stored = credentials._load()
    origin = "ui" if stored.get("image_api_key") else ("env" if get_settings().image_api_key else "")
    next_origin = "ui" if stored.get("image_next_api_key") else ("env" if get_settings().image_next_api_key else "")
    from mediaflow.llm.client import vision_available
    from mediaflow.services.visual import check_enabled

    return ImageSettingsOut(configured=bool(origin), origin=origin, model=images.image_model(), use_refs=images.use_refs(),
                            check=check_enabled(), vision=vision_available(),
                            next_configured=bool(next_origin), next_origin=next_origin,
                            next_exhausted_at=images.next_exhausted_at(), channel=images.active_channel(),
                            models=[ImageModelOut(id=m.id, label=m.label, desc=m.desc) for m in images.MODELS])


@router.get("/image", response_model=ImageSettingsOut)
def get_image_settings():
    return _image_out()


@router.put("/image", response_model=ImageSettingsOut, dependencies=[ADMIN])
def update_image_settings(body: ImageSettingsIn):
    if body.model is not None and body.model and body.model not in {m.id for m in images.MODELS}:
        raise HTTPException(400, "不支持这个配图模型")
    if body.next_api_key is not None:
        credentials.update({"image_next_exhausted": ""})  # 换了 Key 就重新试
    credentials.update({"image_api_key": body.api_key, "image_next_api_key": body.next_api_key, "image_model": body.model,
                        "image_refs": None if body.use_refs is None else ("" if body.use_refs else "off"),
                        "image_check": None if body.check is None else ("" if body.check else "off")})
    return _image_out()


@router.post("/image/test", response_model=ImageTestOut, dependencies=[ADMIN])
async def test_image(body: ImageTestIn):
    """用一句固定的封面描述实际出一张图（会消耗一次生图额度），确认 Key 和模型能用、看看效果。"""
    model = body.model or images.image_model()
    channel = body.channel if body.channel in ("next", "grsai") else (images.active_channel() or "grsai")
    t = time.monotonic()
    try:
        provider = images.channel_provider(channel, model=model, key=(body.api_key or "").strip() or None, fallback=False)
        data = await provider.generate(TEST_PROMPT)
    except images.ImageError as e:
        if channel == "next" and e.exhausted:
            images.mark_next_exhausted()
        return ImageTestOut(ok=False, model=model, channel=channel, seconds=round(time.monotonic() - t, 1), error=str(e))
    if channel == "next" and images.next_exhausted_at():
        images.mark_next_exhausted(False)
    d = get_settings().images_dir / "_test"
    d.mkdir(parents=True, exist_ok=True)
    for old in sorted(d.glob("*.png"))[:-5]:  # 只留最近几张
        old.unlink(missing_ok=True)
    name = f"{int(time.time())}-{model}.png"
    (d / name).write_bytes(data)
    return ImageTestOut(ok=True, model=model, channel=channel, seconds=round(time.monotonic() - t, 1),
                        url=f"/files/images/_test/{name}")


TEST_PROMPT = ("小红书图文笔记封面，竖版 3:4。明亮的窗边书桌，一位二十多岁的中国女生半身近景，笑着举起一本手账，"
               "桌上有拿铁和绿植，自然窗光，手机实拍质感。画面上方大号粗体中文标题「试试AI配图」，深色字配浅色背景，清晰醒目。"
               "不要水印、不要品牌 logo。")
