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
        origin = "ui" if stored.get(sp.key) else ("env" if getattr(s, sp.key, "") else "")
        out.append(CredentialOut(**sp.__dict__, configured=bool(origin), origin=origin))
    return out


@router.get("/credentials", response_model=list[CredentialOut])
def list_credentials():
    return _list()


@router.put("/credentials", response_model=list[CredentialOut])
def update_credentials(body: CredentialsIn):
    credentials.update(body.values)
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
