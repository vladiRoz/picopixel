"""
Component 4 – Global Trend Collector

Runs on a timer and calls fetch() on each registered TrendSource.
Stores combined results in the database.
Adding a new trend source requires no changes here — just register it in main.py.
"""
import asyncio
from datetime import datetime, timedelta

from components.trend_sources.base import TrendSource
from config import config
from storage.store import Store
from utils.logger import get_logger

log = get_logger(__name__)

_CLEANUP_INTERVAL = timedelta(days=30)


class TrendCollector:
    def __init__(self, sources: list[TrendSource], store: Store) -> None:
        self._sources = sources
        self._store = store
        self._last_cleanup: datetime = datetime.utcnow()

    async def run(self) -> None:
        log.info(
            "TrendCollector started — %d source(s): %s (interval=%ds)",
            len(self._sources),
            ", ".join(s.name for s in self._sources),
            config.NEWS_REFRESH_INTERVAL,
        )
        while True:
            try:
                await self._collect()
                self._maybe_cleanup()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("TrendCollector error: %s", exc, exc_info=True)
            await asyncio.sleep(config.NEWS_REFRESH_INTERVAL)

    def _maybe_cleanup(self) -> None:
        if datetime.utcnow() - self._last_cleanup >= _CLEANUP_INTERVAL:
            deleted = self._store.cleanup_old_trends()
            self._last_cleanup = datetime.utcnow()
            log.info("TrendCollector: monthly cleanup removed %d old trend rows", deleted)

    async def _collect(self) -> None:
        trends: list[dict] = []
        for source in self._sources:
            try:
                items = await source.fetch()
                trends.extend(items)
                log.debug("TrendCollector: %s returned %d items", source.name, len(items))
            except Exception as exc:
                log.warning("TrendCollector: source %s failed: %s", source.name, exc)

        if trends:
            self._store.save_trends(trends)
            log.info("TrendCollector: saved %d trend items from %d source(s)", len(trends), len(self._sources))
        else:
            log.warning("TrendCollector: no trends collected from any source")
