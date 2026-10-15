"""并发抓取全部来源，单个来源失败不影响其他来源。"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence

from mediaflow.sources.base import Source, SourceReport, SourceStatus

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
        if err is not None:
            msg = str(err)
            note = f"抓取失败（{msg if 0 < len(msg) <= 40 else type(err).__name__}）"
        elif not items:
            note = "没有拿到结果"
        else:
            note = ""
        report.statuses.append(SourceStatus(
            source=src.name, label=src.label, ok=bool(items), count=len(items), note=note,
        ))
    return report
