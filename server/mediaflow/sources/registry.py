"""并发抓取全部来源，单个来源失败不影响其他来源。"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence

from mediaflow.sources.base import NotConfigured, Source, SourceReport, SourceStatus

logger = logging.getLogger(__name__)


async def fetch_all(keyword: str, limit: int = 8, sources: Sequence[Source] | None = None) -> SourceReport:
    if sources is None:
        from mediaflow.sources.platforms import ALL_SOURCES

        sources = ALL_SOURCES

    async def one(src: Source):
        try:
            return src, await asyncio.wait_for(src.fetch(keyword, limit), timeout=20), None
        except Exception as e:  # noqa: BLE001 - 来源失败一律降级
            logger.warning("[来源:%s] 抓取失败：%s", src.name, e)
            return src, [], e

    report = SourceReport()
    for src, items, err in await asyncio.gather(*(one(s) for s in sources)):
        report.items.extend(items)
        mode = "hot" if items and all(i.kind == "hot" for i in items) else ("search" if items else "")
        if isinstance(err, NotConfigured):
            mode, note = "off", str(err)
        elif err is not None:
            msg = str(err)
            note = f"抓取失败（{msg if 0 < len(msg) <= 60 else type(err).__name__}）"
        elif not items:
            note = "没有搜到结果"
        elif mode == "hot" and keyword:
            note = "没配置搜索，用的热榜（和关键词相关的排前面）"
        else:
            note = ""
        report.statuses.append(SourceStatus(
            source=src.name, label=src.label, ok=bool(items), count=len(items), note=note, mode=mode,
        ))
    return report
