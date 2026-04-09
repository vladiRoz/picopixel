"""
Unified schema for a parsed Telegram coin signal.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class EventType(str, Enum):
    WHALE_BUY = "whale_buy"
    ACCUMULATION = "accumulation"
    ANOTHER_WHALE = "another_whale"
    ENTRY_SIGNAL = "entry_signal"
    GAIN_UPDATE = "gain_update"
    SUMMARY = "summary"
    UNKNOWN = "unknown"


@dataclass
class CoinSignal:
    # Identity
    coin_name: str
    symbol: str
    event_type: EventType

    # Source
    channel: str
    raw_message: str
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # Market data
    market_cap: Optional[float] = None          # current MC in USD
    top_market_cap: Optional[float] = None      # ATH MC since signal
    liquidity: Optional[float] = None           # USD
    volume_1h: Optional[float] = None           # USD

    # Participants
    holders: Optional[int] = None
    wallet_size_sol: Optional[float] = None     # whale wallet size
    buy_amount_sol: Optional[float] = None      # amount bought
    buy_percentage: Optional[float] = None      # % of supply bought

    # Token health
    age_minutes: Optional[int] = None
    security_flags: list[str] = field(default_factory=list)
    dev_sold: Optional[float] = None            # % dev sold
    bundled_pct: Optional[float] = None

    # Gain tracking
    gain_percentage: Optional[float] = None     # for gain_update events
    source_entry_mc: Optional[float] = None     # MC at entry signal
    current_mc: Optional[float] = None          # current MC for gain calc

    # Summary entries (for summary events, list of (name, symbol, gain_x))
    summary_entries: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "coin_name": self.coin_name,
            "symbol": self.symbol,
            "event_type": self.event_type.value,
            "channel": self.channel,
            "timestamp": self.timestamp.isoformat(),
            "market_cap": self.market_cap,
            "top_market_cap": self.top_market_cap,
            "liquidity": self.liquidity,
            "volume_1h": self.volume_1h,
            "holders": self.holders,
            "wallet_size_sol": self.wallet_size_sol,
            "buy_amount_sol": self.buy_amount_sol,
            "buy_percentage": self.buy_percentage,
            "age_minutes": self.age_minutes,
            "security_flags": self.security_flags,
            "gain_percentage": self.gain_percentage,
            "summary_entries": self.summary_entries,
        }
