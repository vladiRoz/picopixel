"""
Component 6 – Meta Discovery & Self-Learning Loop

Periodically reviews coins in the analysis queue results, compares
assigned metas against the meta map, and registers new metas when
they don't exist yet.

Also processes human feedback to correct meta assignments.
"""
import asyncio
from datetime import datetime

from components.meta_mapping import MetaMap
from storage.store import Store
from utils.logger import get_logger

log = get_logger(__name__)


class MetaDiscovery:
    def __init__(
        self,
        analysis_queue: asyncio.Queue,
        meta_map: MetaMap,
        store: Store,
        broadcast_queue: asyncio.Queue,
    ) -> None:
        self._analysis_q = analysis_queue
        self._meta_map = meta_map
        self._store = store
        self._broadcast_q = broadcast_queue  # (signal, metas, meta_ids) for evaluation

    async def run(self) -> None:
        log.info("MetaDiscovery started")
        while True:
            try:
                signal, metas = await self._analysis_q.get()
                meta_ids = self._process(signal.symbol, metas)
                await self._broadcast_q.put((signal, metas, meta_ids))
                self._analysis_q.task_done()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("MetaDiscovery error: %s", exc, exc_info=True)

    def _process(self, symbol: str, metas: list[str]) -> list[str]:
        """Register new metas if they don't exist; return list of meta IDs."""
        meta_ids = []
        for meta_name in metas:
            meta = self._meta_map.find_or_create(meta_name)
            self._meta_map.add_coin_to_meta(meta.id, symbol)
            meta_ids.append(meta.id)
            if meta.is_emerging:
                log.info("Emerging meta detected: %s (coin: %s)", meta_name, symbol)
        return meta_ids

    def apply_feedback(self, coin_symbol: str, old_metas: list[str], new_metas: list[str], note: str = "") -> None:
        """
        Called by FeedbackServer when a user corrects a meta assignment.
        Saves the correction and reprocesses the coin under the new metas.
        """
        self._store.save_feedback(coin_symbol, old_metas, new_metas, note)
        self._process(coin_symbol, new_metas)
        log.info(
            "Feedback applied for %s: %s -> %s",
            coin_symbol, old_metas, new_metas,
        )
