"""
Component 3 – Meta Analysis Engine

Consumes CoinSignal objects, uses GPT-4o-mini to assign one or more metas,
and puts (CoinSignal, metas) tuples onto the analysis queue.
"""
import asyncio
import json
from typing import Optional

from openai import AsyncOpenAI

from config import config
from models.coin import CoinSignal
from storage.store import Store
from utils.logger import get_logger

log = get_logger(__name__)

_SYSTEM_PROMPT = """You are a crypto meme coin meta analyst.

A "meta" is the underlying real-world narrative or trend driving attention toward a coin.
Examples of metas: AI/Tech, Politics/Trump, War/Geopolitics, Animals/Memes, Finance/Economy,
Sports, Entertainment, Food/Lifestyle, Environment, Religion/Culture, Gaming, Music, Science.

Given a coin name, symbol, and optional context (market cap, volume, message type), return:
1. A list of 1–3 meta labels that best describe this coin's narrative.
2. A short reasoning sentence.

Rules:
- If the coin name clearly maps to a current event (e.g., a politician, a conflict, a tech trend),
  use that as the meta.
- Be specific: "Trump/Politics" beats "Politics".
- If genuinely unclear, use "Unknown/Meme".
- Respond ONLY with valid JSON: {"metas": ["Meta1", "Meta2"], "reasoning": "..."}"""


class MetaAnalysisEngine:
    def __init__(
        self,
        parsed_queue: asyncio.Queue,
        analysis_queue: asyncio.Queue,
        store: Store,
    ) -> None:
        self._parsed_q = parsed_queue
        self._analysis_q = analysis_queue
        self._store = store
        self._openai: Optional[AsyncOpenAI] = (
            AsyncOpenAI(api_key=config.OPENROUTER_API_KEY, base_url=config.OPENROUTER_BASE_URL)
            if config.OPENROUTER_API_KEY else None
        )

    async def run(self) -> None:
        log.info("MetaAnalysisEngine started")
        while True:
            try:
                signal: CoinSignal = await self._parsed_q.get()
                metas = await self._assign_metas(signal)
                await self._analysis_q.put((signal, metas))
                log.info(
                    "Meta assigned for %s: %s", signal.symbol, metas
                )
                self._parsed_q.task_done()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("MetaAnalysisEngine error: %s", exc, exc_info=True)

    async def _assign_metas(self, signal: CoinSignal) -> list[str]:
        if not self._openai:
            return ["Unknown/Meme"]

        user_content = self._build_prompt(signal)
        try:
            resp = await self._openai.chat.completions.create(
                model=config.OPENROUTER_MODEL,
                max_tokens=config.OPENROUTER_MAX_TOKENS,
                temperature=config.OPENROUTER_TEMPERATURE,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
            )
            data = json.loads(resp.choices[0].message.content)
            metas = data.get("metas", [])
            if not metas:
                return ["Unknown/Meme"]
            return [str(m).strip() for m in metas[:3]]
        except Exception as exc:
            log.warning("LLM meta assignment failed for %s: %s", signal.symbol, exc)
            return ["Unknown/Meme"]

    def _build_prompt(self, signal: CoinSignal) -> str:
        parts = [
            f"Coin name: {signal.coin_name}",
            f"Symbol: {signal.symbol}",
            f"Event type: {signal.event_type.value}",
            f"Channel: {signal.channel}",
        ]
        if signal.market_cap:
            parts.append(f"Market cap: ${signal.market_cap:,.0f}")
        if signal.volume_1h:
            parts.append(f"Volume (1h): ${signal.volume_1h:,.0f}")
        if signal.gain_percentage:
            parts.append(f"Gain: {signal.gain_percentage}%")
        # Include a short snippet of the raw message for extra context
        snippet = signal.raw_message[:200].replace("\n", " ")
        parts.append(f"Message snippet: {snippet}")
        return "\n".join(parts)
