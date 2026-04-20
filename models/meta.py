"""
Meta (narrative/trend) and evaluation models.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


@dataclass
class Meta:
    id: str                                     # slug, e.g. "ai-tech"
    name: str                                   # display name, e.g. "AI / Tech"
    description: str
    keywords: list[str] = field(default_factory=list)
    strength: float = 0.5                       # 0.0 – 1.0
    trend_alignment: float = 0.0               # correlation with global trends
    coins: list[str] = field(default_factory=list)   # symbols
    is_emerging: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "keywords": self.keywords,
            "strength": self.strength,
            "trend_alignment": self.trend_alignment,
            "coins": self.coins,
            "is_emerging": self.is_emerging,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Meta":
        return cls(
            id=d["id"],
            name=d["name"],
            description=d.get("description", ""),
            keywords=d.get("keywords", []),
            strength=d.get("strength", 0.5),
            trend_alignment=d.get("trend_alignment", 0.0),
            coins=d.get("coins", []),
            is_emerging=d.get("is_emerging", False),
            created_at=datetime.fromisoformat(d["created_at"]) if "created_at" in d else datetime.utcnow(),
            updated_at=datetime.fromisoformat(d["updated_at"]) if "updated_at" in d else datetime.utcnow(),
        )


class Recommendation(str, Enum):
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    WATCH = "watch"
    AVOID = "avoid"


@dataclass
class CoinEvaluation:
    coin_symbol: str
    coin_name: str
    metas: list[str]                            # meta IDs
    meta_strength: float                        # 0.0 – 1.0
    trend_alignment: float                      # 0.0 – 1.0
    whale_activity_score: float                 # 0.0 – 1.0
    momentum_score: float                       # 0.0 – 1.0
    overall_score: float                        # 0.0 – 1.0
    recommendation: Recommendation
    reasoning: str
    channel: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "coin_symbol": self.coin_symbol,
            "coin_name": self.coin_name,
            "metas": self.metas,
            "meta_strength": self.meta_strength,
            "trend_alignment": self.trend_alignment,
            "whale_activity_score": self.whale_activity_score,
            "momentum_score": self.momentum_score,
            "overall_score": self.overall_score,
            "recommendation": self.recommendation.value,
            "reasoning": self.reasoning,
            "channel": self.channel,
            "timestamp": self.timestamp.isoformat(),
        }
