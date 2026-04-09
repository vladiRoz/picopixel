"""
Component 2 – Message Parser & Normalizer

Consumes RawMessage objects from the raw queue, parses them into CoinSignal
objects using regex patterns, and puts results onto the parsed queue.
Falls back to LLM only when regex cannot extract a symbol at all.
"""
import asyncio
import json
import re
from typing import Optional

from openai import AsyncOpenAI

from components.telegram_listener import RawMessage
from config import config
from models.coin import CoinSignal, EventType
from storage.store import Store
from utils.logger import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Regex helpers
# ---------------------------------------------------------------------------

# Parse compact number notation: $452,198 / $61.9K / $2.2M
_NUM_RE = re.compile(r"\$?([\d,]+\.?\d*)([KkMmBb]?)")


def _parse_usd(text: str) -> Optional[float]:
    m = _NUM_RE.search(text.replace(",", ""))
    if not m:
        return None
    val = float(m.group(1).replace(",", ""))
    suffix = m.group(2).upper()
    if suffix == "K":
        val *= 1_000
    elif suffix == "M":
        val *= 1_000_000
    elif suffix == "B":
        val *= 1_000_000_000
    return val


def _parse_sol(text: str) -> Optional[float]:
    m = re.search(r"([\d.]+)\s*SOL", text)
    return float(m.group(1)) if m else None


def _parse_holders(text: str) -> Optional[int]:
    m = re.search(r"Hodls:\s*(\d+)", text)
    return int(m.group(1)) if m else None


def _parse_age(text: str) -> Optional[int]:
    """Return age in minutes."""
    m = re.search(r"Age:\s*(\d+)([mhd])", text, re.IGNORECASE)
    if not m:
        return None
    val, unit = int(m.group(1)), m.group(2).lower()
    if unit == "h":
        val *= 60
    elif unit == "d":
        val *= 1440
    return val


def _parse_security(text: str) -> list[str]:
    flags = []
    if "🚨" in text:
        flags.append("high_risk")
    if "⚠️" in text or "⚠" in text:
        flags.append("warning")
    if "🤍" in text:
        flags.append("clean")
    return flags


def _extract_mc(text: str) -> Optional[float]:
    m = re.search(r"MC:\s*\$?([\d,.KkMm]+)", text)
    return _parse_usd(m.group(1)) if m else None


def _extract_top_mc(text: str) -> Optional[float]:
    m = re.search(r"🔝\s*\$?([\d,.KkMm]+)", text)
    return _parse_usd(m.group(1)) if m else None


def _extract_liq(text: str) -> Optional[float]:
    m = re.search(r"Liq:\s*\$?([\d,.KkMm]+)", text)
    return _parse_usd(m.group(1)) if m else None


def _extract_vol(text: str) -> Optional[float]:
    m = re.search(r"Vol[^:]*:\s*\$?([\d,.KkMm]+)", text)
    return _parse_usd(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# Event-type-specific parsers
# ---------------------------------------------------------------------------

def _parse_whale_buy(text: str, channel: str, timestamp) -> Optional[CoinSignal]:
    """Matches: 🔥 Name New Whale Buy! / 🌊🐳 Another Whale Aped $SYM! / ➕🐳 Whale Accumulating $SYM!"""
    event_type = EventType.WHALE_BUY
    coin_name = ""
    symbol = ""

    m = re.search(r"🔥\s+(.+?)\s+New Whale Buy!", text)
    if m:
        coin_name = m.group(1).strip()
        event_type = EventType.WHALE_BUY
    else:
        m = re.search(r"Another Whale Aped\s+\$(\w+)!", text)
        if m:
            symbol = m.group(1)
            coin_name = symbol
            event_type = EventType.ANOTHER_WHALE
        else:
            m = re.search(r"Whale Accumulating\s+\$(\w+)!", text)
            if m:
                symbol = m.group(1)
                coin_name = symbol
                event_type = EventType.ACCUMULATION

    if not coin_name:
        return None

    # Extract symbol from buy line: 💸 2.04 SOL → 0.09% $SYMBOL
    if not symbol:
        sm = re.search(r"\$(\w+)\s*$", text, re.MULTILINE)
        if sm:
            symbol = sm.group(1)
        else:
            symbol = coin_name.upper().replace(" ", "")

    # Wallet and buy amount
    wallet_sol = _parse_sol(text.split("Wallet:")[1]) if "Wallet:" in text else None
    buy_sol = None
    buy_pct = None
    bm = re.search(r"💸\s*([\d.]+)\s*SOL\s*→\s*([\d.]+)%", text)
    if bm:
        buy_sol = float(bm.group(1))
        buy_pct = float(bm.group(2))

    return CoinSignal(
        coin_name=coin_name,
        symbol=symbol.upper(),
        event_type=event_type,
        channel=channel,
        raw_message=text,
        timestamp=timestamp,
        market_cap=_extract_mc(text),
        top_market_cap=_extract_top_mc(text),
        liquidity=_extract_liq(text),
        volume_1h=_extract_vol(text),
        holders=_parse_holders(text),
        wallet_size_sol=wallet_sol,
        buy_amount_sol=buy_sol,
        buy_percentage=buy_pct,
        age_minutes=_parse_age(text),
        security_flags=_parse_security(text),
    )


def _parse_entry_signal(text: str, channel: str, timestamp) -> Optional[CoinSignal]:
    """Matches: 🔥 Name New Trending"""
    m = re.search(r"🔥\s+(.+?)\s+New Trending", text)
    if not m:
        return None
    coin_name = m.group(1).strip()
    symbol_match = re.search(r"\$(\w+)", text)
    symbol = symbol_match.group(1) if symbol_match else coin_name.upper().replace(" ", "")

    return CoinSignal(
        coin_name=coin_name,
        symbol=symbol.upper(),
        event_type=EventType.ENTRY_SIGNAL,
        channel=channel,
        raw_message=text,
        timestamp=timestamp,
        market_cap=_extract_mc(text),
        top_market_cap=_extract_top_mc(text),
        liquidity=_extract_liq(text),
        volume_1h=_extract_vol(text),
        holders=_parse_holders(text),
        age_minutes=_parse_age(text),
        security_flags=_parse_security(text),
    )


def _parse_gain_update(text: str, channel: str, timestamp) -> Optional[CoinSignal]:
    """Matches: 📈 SYMBOL is up X% 📈"""
    m = re.search(r"📈\s+(\w+)\s+is up\s+([\d.]+)%\s+📈", text)
    if not m:
        return None
    symbol = m.group(1)
    gain = float(m.group(2))

    # Extract MC range: $164K —> $248.3K
    mcs = re.findall(r"\$?([\d,.KkMm]+)", text)
    source_mc = _parse_usd(mcs[0]) if len(mcs) > 0 else None
    current_mc = _parse_usd(mcs[1]) if len(mcs) > 1 else None

    return CoinSignal(
        coin_name=symbol,
        symbol=symbol.upper(),
        event_type=EventType.GAIN_UPDATE,
        channel=channel,
        raw_message=text,
        timestamp=timestamp,
        gain_percentage=gain,
        source_entry_mc=source_mc,
        current_mc=current_mc,
        market_cap=current_mc,
    )


def _parse_summary(text: str, channel: str, timestamp) -> Optional[CoinSignal]:
    """
    Matches summary blocks. Two formats:
    - "🥇 Name | SYMBOL | X%"  (Whale Trending)
    - "🥇 Name | $SYMBOL • X X [src]"  (Solana Early)
    """
    entries = []

    # Format 1: Name | SYMBOL | X%
    for m in re.finditer(
        r"([A-Za-z0-9\s\u4e00-\u9fff\u30a0-\u30ff]+?)\s*\|\s*(\w+)\s*\|\s*([\d.KkMm]+)%",
        text,
    ):
        entries.append({
            "name": m.group(1).strip(),
            "symbol": m.group(2).upper(),
            "gain_pct": float(m.group(3).replace("K", "000").replace("k", "000")),
        })

    # Format 2: Name | $SYMBOL • X X
    for m in re.finditer(
        r"([A-Za-z0-9\s]+?)\s*\|\s*\$(\w+)\s*•\s*([\d]+)X",
        text,
    ):
        entries.append({
            "name": m.group(1).strip(),
            "symbol": m.group(2).upper(),
            "gain_x": int(m.group(3)),
        })

    if not entries:
        return None

    # Use the first entry as the representative signal
    first = entries[0]
    return CoinSignal(
        coin_name=first.get("name", first["symbol"]),
        symbol=first["symbol"],
        event_type=EventType.SUMMARY,
        channel=channel,
        raw_message=text,
        timestamp=timestamp,
        gain_percentage=first.get("gain_pct"),
        summary_entries=entries,
    )


# ---------------------------------------------------------------------------
# LLM fallback
# ---------------------------------------------------------------------------

_FALLBACK_PROMPT = """You receive a raw Telegram message from a crypto meme coin channel.
Extract the coin symbol and coin name. If you cannot determine either, return null for both.
Respond ONLY with valid JSON: {"symbol": "SYMBOL_OR_NULL", "coin_name": "Name or null"}"""


async def _llm_extract_symbol(text: str, client: AsyncOpenAI) -> tuple[str, str]:
    try:
        resp = await client.chat.completions.create(
            model=config.OPENAI_MODEL,
            max_tokens=64,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _FALLBACK_PROMPT},
                {"role": "user", "content": text[:500]},
            ],
        )
        data = json.loads(resp.choices[0].message.content)
        symbol = data.get("symbol") or ""
        name = data.get("coin_name") or symbol
        return symbol.upper(), name
    except Exception as exc:
        log.warning("LLM symbol extraction failed: %s", exc)
        return "", ""


# ---------------------------------------------------------------------------
# Parser component
# ---------------------------------------------------------------------------

class MessageParser:
    def __init__(
        self,
        raw_queue: asyncio.Queue,
        parsed_queue: asyncio.Queue,
        store: Store,
    ) -> None:
        self._raw_q = raw_queue
        self._parsed_q = parsed_queue
        self._store = store
        self._openai = AsyncOpenAI(api_key=config.OPENAI_API_KEY) if config.OPENAI_API_KEY else None

    async def run(self) -> None:
        log.info("MessageParser started")
        while True:
            try:
                raw: RawMessage = await self._raw_q.get()
                signal = await self._parse(raw)
                if signal:
                    self._store.save_signal(signal)
                    await self._parsed_q.put(signal)
                    log.info(
                        "Parsed [%s] %s/%s from %s",
                        signal.event_type.value,
                        signal.coin_name,
                        signal.symbol,
                        signal.channel,
                    )
                self._raw_q.task_done()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("MessageParser error: %s", exc, exc_info=True)

    async def _parse(self, raw: RawMessage) -> Optional[CoinSignal]:
        text = raw.text
        ts = raw.timestamp
        ch = raw.channel

        # Try each known pattern
        for parser_fn in (
            _parse_whale_buy,
            _parse_entry_signal,
            _parse_gain_update,
            _parse_summary,
        ):
            result = parser_fn(text, ch, ts)
            if result:
                return result

        # LLM fallback — only if OpenAI is configured
        if self._openai:
            symbol, name = await _llm_extract_symbol(text, self._openai)
            if symbol:
                return CoinSignal(
                    coin_name=name or symbol,
                    symbol=symbol,
                    event_type=EventType.UNKNOWN,
                    channel=ch,
                    raw_message=text,
                    timestamp=ts,
                )

        log.debug("Could not parse message (len=%d): %s…", len(text), text[:60])
        return None
