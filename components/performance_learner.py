"""
Component 9 – Performance Learner

Consumes PERF_RESULT and PERF_SUMMARY signals from the perf_queue.
For each coin it:
  1. Looks up the most recent evaluation the system made for that coin.
  2. Compares the prediction (recommendation + score) against the actual
     performance (gain multiplier from the channel).
  3. Adjusts the strength of the metas that were assigned to that coin —
     reinforcing metas that predicted well, penalising those that didn't.
  4. Persists the outcome record so the web UI can display learning history.

Learning rules (applied per meta assigned to the coin):
  - STRONG_BUY/BUY + gain >= 5X  → correct call   → strength +0.06
  - STRONG_BUY/BUY + gain < 2X   → wrong call      → strength -0.08
  - WATCH/AVOID   + gain >= 10X  → missed opp      → strength +0.03  (meta valid, score too low)
  - WATCH/AVOID   + gain < 5X    → correct pass    → strength +0.02
  - All other cases               → neutral          → no change

Strength is always clamped to [0.1, 1.0].
"""
import asyncio
from typing import Optional

from components.meta_mapping import MetaMap
from models.coin import CoinSignal, EventType
from storage.store import Store
from utils.logger import get_logger

log = get_logger(__name__)

# Gain thresholds for judging outcomes
_GOOD_GAIN = 5.0    # 5X+ = successful trade
_GREAT_GAIN = 10.0  # 10X+ = exceptional
_BAD_GAIN = 2.0     # <2X = not worth it

# Strength deltas
_DELTA_CORRECT = +0.06
_DELTA_WRONG = -0.08
_DELTA_MISSED = +0.03
_DELTA_CORRECT_PASS = +0.02

_BUY_RECS = {"strong_buy", "buy"}
_PASS_RECS = {"watch", "avoid"}


def _judge(recommendation: Optional[str], gain_x: float) -> tuple[int, float]:
    """
    Returns (was_correct, delta) where:
      was_correct:  1=correct, 0=neutral, -1=wrong/missed
      delta:        raw strength adjustment to apply
    """
    rec = (recommendation or "").lower()
    if rec in _BUY_RECS:
        if gain_x >= _GOOD_GAIN:
            return 1, _DELTA_CORRECT
        elif gain_x < _BAD_GAIN:
            return -1, _DELTA_WRONG
    elif rec in _PASS_RECS:
        if gain_x >= _GREAT_GAIN:
            return -1, _DELTA_MISSED
        elif gain_x < _GOOD_GAIN:
            return 1, _DELTA_CORRECT_PASS
    return 0, 0.0


class PerformanceLearner:
    def __init__(
        self,
        perf_queue: asyncio.Queue,
        meta_map: MetaMap,
        store: Store,
    ) -> None:
        self._perf_q = perf_queue
        self._meta_map = meta_map
        self._store = store

    async def run(self) -> None:
        log.info("PerformanceLearner started")
        while True:
            try:
                signal: CoinSignal = await self._perf_q.get()
                if signal.event_type == EventType.PERF_RESULT:
                    await self._learn_single(signal)
                elif signal.event_type == EventType.PERF_SUMMARY:
                    await self._learn_summary(signal)
                self._perf_q.task_done()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("PerformanceLearner error: %s", exc, exc_info=True)

    async def _learn_single(self, signal: CoinSignal) -> None:
        gain_x = signal.gain_multiplier or 0.0
        await self._process_coin(
            symbol=signal.symbol,
            coin_name=signal.coin_name,
            gain_x=gain_x,
            source_mc=signal.source_entry_mc,
            current_mc=signal.current_mc,
        )

    async def _learn_summary(self, signal: CoinSignal) -> None:
        for entry in signal.summary_entries:
            await self._process_coin(
                symbol=entry["symbol"],
                coin_name=entry.get("name", entry["symbol"]),
                gain_x=float(entry.get("gain_x", 0)),
                source_mc=None,
                current_mc=None,
            )

    async def _process_coin(
        self,
        symbol: str,
        coin_name: str,
        gain_x: float,
        source_mc: Optional[float],
        current_mc: Optional[float],
    ) -> None:
        ev = self._store.get_latest_evaluation_for_symbol(symbol)

        prediction = ev["recommendation"] if ev else None
        overall_score = ev["overall_score"] if ev else None
        meta_ids: list[str] = ev["metas"] if ev else []

        was_correct, delta = _judge(prediction, gain_x)

        # Apply strength adjustment to each meta assigned to this coin
        if delta != 0.0 and meta_ids:
            for meta_id in meta_ids:
                meta = self._meta_map.get_meta(meta_id)
                if meta:
                    new_strength = max(0.1, min(1.0, meta.strength + delta))
                    self._meta_map.update_strength(meta_id, new_strength)

        # Update co-occurrence performance stats for this coin's meta pairs
        if gain_x > 0 and meta_ids:
            self._store.update_cooccurrence_performance(meta_ids, gain_x)

        # Persist the outcome
        self._store.save_performance_outcome(
            coin_symbol=symbol,
            coin_name=coin_name,
            gain_multiplier=gain_x,
            source_entry_mc=source_mc,
            current_mc=current_mc,
            prediction=prediction,
            overall_score=overall_score,
            metas=meta_ids,
            was_correct=was_correct,
            meta_adjustment=delta,
        )

        label = {1: "correct", 0: "neutral", -1: "wrong/missed"}[was_correct]
        log.info(
            "PerformanceLearner: %s %.0fX | prediction=%s | verdict=%s | meta_delta=%.2f | metas=%s",
            symbol,
            gain_x,
            prediction or "none",
            label,
            delta,
            meta_ids,
        )
