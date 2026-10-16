"""热点来源统一接口：每个平台一个文件，实现 `Source.fetch`。

约定：来源失败只影响自己，绝不抛到上层；状态如实汇报给用户。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)


@dataclass
class TrendItem:
    title: str
    source: str
    url: str = ""
    heat: str = ""
    snippet: str = ""
    kind: str = "search"  # "search" 关键词搜索结果；"hot" 热榜兜底
    ref: str = ""         # 平台内部定位串，可交给调研能力看详情（热榜条目为空）


@dataclass
class SourceStatus:
    source: str
    label: str
    ok: bool
    count: int = 0
    note: str = ""
    mode: str = ""  # "search" | "hot" | "off"（没配置凭据，未启用）


@dataclass
class SourceReport:
    items: list[TrendItem] = field(default_factory=list)
    statuses: list[SourceStatus] = field(default_factory=list)

    @property
    def failed_labels(self) -> list[str]:
        return [s.label for s in self.statuses if not s.ok and s.mode != "off"]

    @property
    def enabled(self) -> list[SourceStatus]:
        return [s for s in self.statuses if s.mode != "off"]


class NotConfigured(RuntimeError):
    """来源需要的凭据没配置：不算失败，只标记为未启用。"""


class Source(Protocol):
    name: str
    label: str

    async def fetch(self, keyword: str, limit: int) -> list[TrendItem]: ...
