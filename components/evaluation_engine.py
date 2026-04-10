"""
Component 8 – Evaluation Engine

Consumes (signal, metas, meta_ids) tuples from the broadcast queue.
Generates a structured CoinEvaluation and persists it.
"""
import asyncio
import json
from typing import Optional

from openai import AsyncOpenAI

from components.meta_mapping import MetaMap
from config import config
from models.coin import CoinSignal, EventType
from models.meta import CoinEvaluation, Recommendation
from storage.store import Store
from utils.logger import get_logger

log = get_logger(__name__)

_EVAL_PROMPT = """You are a crypto meme coin analyst. Given the data below, produce a concise
evaluation. Respond ONLY with valid JSON matching this schema:
{
  "recommendation": "strong_buy" | "buy" | "watch" | "avoid",
  "reasoning": "one or two sentences"
}

Criteria:
- strong_buy: meta is hot + strong trend alignment + whale activity + momentum
- buy: meta is relevant, decent signals
- watch: interesting meta but insufficient confirmation
- avoid: weak meta, bad signals, or just noise"""


class EvaluationEngine:
    def __init__(
        self,
        broadcast_queue: asyncio.Queue,
        meta_map: MetaMap,
        store: Store,
    ) -> None:
        self._broadcast_q = broadcast_queue
        self._meta_map = meta_map
        self._store = store
        self._openai: Optional[AsyncOpenAI] = (
            AsyncOpenAI(api_key=config.OPENROUTER_API_KEY, base_url=config.OPENROUTER_BASE_URL)
            if config.OPENROUTER_API_KEY else None
        )

    async def run(self) -> None:
        log.info("EvaluationEngine started")
        while True:
            try:
                signal, metas, meta_ids = await self._broadcast_q.get()
                ev = await self._evaluate(signal, metas, meta_ids)
                self._store.save_evaluation(ev)
                log.info(
                    "Evaluation: %s → %s (score=%.2f)",
                    signal.symbol,
                    ev.recommendation.value,
                    ev.overall_score,
                )
                self._broadcast_q.task_done()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("EvaluationEngine error: %s", exc, exc_info=True)

    async def _evaluate(
        self, signal: CoinSignal, metas: list[str], meta_ids: list[str]
    ) -> CoinEvaluation:
        # Gather meta strengths
        meta_objects = [self._meta_map.get_meta(mid) for mid in meta_ids if self._meta_map.get_meta(mid)]
        meta_strength = (
            sum(m.strength for m in meta_objects) / len(meta_objects)
            if meta_objects else 0.3
        )
        trend_alignment = (
            sum(m.trend_alignment for m in meta_objects) / len(meta_objects)
            if meta_objects else 0.0
        )

        # Whale activity score
        whale_score = self._whale_score(signal)

        # Momentum score (gain updates and high volume)
        momentum_score = self._momentum_score(signal)

        # Overall
        overall = (
            meta_strength * 0.35
            + trend_alignment * 0.25
            + whale_score * 0.25
            + momentum_score * 0.15
        )

        # Recommendation via LLM if available, else rule-based
        recommendation, reasoning = await self._recommend(
            signal, metas, meta_strength, trend_alignment, whale_score, momentum_score, overall
        )

        return CoinEvaluation(
            coin_symbol=signal.symbol,
            coin_name=signal.coin_name,
            metas=meta_ids,
            meta_strength=round(meta_strength, 3),
            trend_alignment=round(trend_alignment, 3),
            whale_activity_score=round(whale_score, 3),
            momentum_score=round(momentum_score, 3),
            overall_score=round(overall, 3),
            recommendation=recommendation,
            reasoning=reasoning,
            timestamp=signal.timestamp,
        )

    def _whale_score(self, signal: CoinSignal) -> float:
        score = 0.0
        if signal.event_type in (EventType.WHALE_BUY, EventType.ANOTHER_WHALE, EventType.ACCUMULATION):
            score += 0.5
        if signal.wallet_size_sol and signal.wallet_size_sol >= 100:
            score += 0.2
        if signal.buy_amount_sol and signal.buy_amount_sol >= 2:
            score += 0.2
        if signal.holders and signal.holders >= 1000:
            score += 0.1
        return min(1.0, score)

    def _momentum_score(self, signal: CoinSignal) -> float:
        score = 0.0
        if signal.gain_percentage:
            score += min(0.5, signal.gain_percentage / 200)
        if signal.volume_1h and signal.volume_1h >= 100_000:
            score += 0.3
        if signal.market_cap and signal.top_market_cap:
            if signal.top_market_cap > signal.market_cap * 1.5:
                score += 0.2  # has run hard previously
        return min(1.0, score)

    async def _recommend(
        self,
        signal: CoinSignal,
        metas: list[str],
        meta_strength: float,
        trend_alignment: float,
        whale_score: float,
        momentum_score: float,
        overall: float,
    ) -> tuple[Recommendation, str]:
        if self._openai:
            try:
                user_content = json.dumps({
                    "coin": signal.coin_name,
                    "symbol": signal.symbol,
                    "metas": metas,
                    "meta_strength": round(meta_strength, 2),
                    "trend_alignment": round(trend_alignment, 2),
                    "whale_score": round(whale_score, 2),
                    "momentum_score": round(momentum_score, 2),
                    "overall_score": round(overall, 2),
                    "event_type": signal.event_type.value,
                    "market_cap": signal.market_cap,
                    "gain_pct": signal.gain_percentage,
                })
                resp = await self._openai.chat.completions.create(
                    model=config.OPENROUTER_MODEL,
                    max_tokens=150,
                    temperature=0,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": _EVAL_PROMPT},
                        {"role": "user", "content": user_content},
                    ],
                )
                data = json.loads(resp.choices[0].message.content)
                rec_str = data.get("recommendation", "watch").lower()
                rec = Recommendation(rec_str) if rec_str in Recommendation._value2member_map_ else Recommendation.WATCH
                reasoning = data.get("reasoning", "")
                return rec, reasoning
            except Exception as exc:
                log.warning("LLM recommendation failed: %s", exc)

        # Rule-based fallback
        if overall >= 0.7:
            return Recommendation.STRONG_BUY, "High composite score across meta, trends, and whale activity."
        if overall >= 0.5:
            return Recommendation.BUY, "Solid signals with reasonable meta alignment."
        if overall >= 0.3:
            return Recommendation.WATCH, "Some positive signals but insufficient confirmation."
        return Recommendation.AVOID, "Weak meta and minimal on-chain confirmation."
