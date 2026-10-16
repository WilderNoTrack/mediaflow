"""数据来源设置：查看/填写各平台搜索凭据，并实测一次。"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from mediaflow import credentials
from mediaflow.config import get_settings
from mediaflow.domain.schemas import SourceStatusOut
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
