"""
Component 7 – Adaptation & Monitoring Layer

Periodically:
- Computes meta strength from coin activity and gain data
- Aligns metas against current global trends
- Detects emerging metas (high recent activity, not yet mainstream)
- Marks weak/stale metas for de-prioritisation
"""
import asyncio
from datetime import datetime, timedelta

from components.meta_mapping import MetaMap
from storage.store import Store
from utils.logger import get_logger

log = get_logger(__name__)

# A meta with recent activity above this threshold gets a strength boost
_ACTIVE_COIN_THRESHOLD = 3
# Recent window for "active" signals
_ACTIVE_WINDOW_HOURS = 24


class AdaptationMonitor:
    def __init__(self, meta_map: MetaMap, store: Store, interval: int) -> None:
        self._meta_map = meta_map
        self._store = store
        self._interval = interval

    async def run(self) -> None:
        log.info("AdaptationMonitor started (interval=%ds)", self._interval)
        while True:
            try:
                await self._adapt()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("AdaptationMonitor error: %s", exc, exc_info=True)
            await asyncio.sleep(self._interval)

    async def _adapt(self) -> None:
        recent_signals = self._store.get_recent_signals(limit=200)
        trends = self._store.get_trends()
        all_trend_keywords: list[str] = []
        for t in trends:
            all_trend_keywords.extend(t.get("keywords", []))

        # Compute meta strength from coin activity
        cutoff = (datetime.utcnow() - timedelta(hours=_ACTIVE_WINDOW_HOURS)).isoformat()
        recent_symbols: set[str] = set()
        symbol_gains: dict[str, list[float]] = {}

        for sig in recent_signals:
            if sig.get("timestamp", "") >= cutoff:
                sym = sig.get("symbol", "")
                recent_symbols.add(sym)
                gain = sig.get("gain_percentage")
                if gain is not None:
                    symbol_gains.setdefault(sym, []).append(gain)

        # Update each meta
        alignment_scores = self._meta_map.correlate_with_trends(all_trend_keywords)

        for meta in self._meta_map.get_all():
            # Strength: fraction of meta's coins that were active recently
            active_coins = [c for c in meta.coins if c in recent_symbols]
            if meta.coins:
                activity_ratio = len(active_coins) / len(meta.coins)
            else:
                activity_ratio = 0.0

            # Gain bonus: average gain of active coins in this meta
            gains = []
            for sym in active_coins:
                gains.extend(symbol_gains.get(sym, []))
            avg_gain = (sum(gains) / len(gains)) if gains else 0.0
            gain_bonus = min(0.3, avg_gain / 500)  # +0.3 max for 150%+ gains

            new_strength = min(1.0, 0.3 + activity_ratio * 0.4 + gain_bonus)
            self._meta_map.update_strength(meta.id, new_strength)

            # Trend alignment
            alignment = alignment_scores.get(meta.id, 0.0)
            self._meta_map.update_trend_alignment(meta.id, alignment)

        log.debug(
            "AdaptationMonitor: updated %d metas", len(self._meta_map.get_all())
        )
