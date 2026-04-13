"""
Abstract base class for all trend sources.
Each source returns a list of trend dicts: {title, source, keywords}.
"""
from abc import ABC, abstractmethod


class TrendSource(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable source identifier shown in logs."""

    @abstractmethod
    async def fetch(self) -> list[dict]:
        """
        Fetch current trends from this source.
        Returns list of dicts: {"title": str, "source": str, "keywords": list[str]}
        Must not raise — return [] on failure and log internally.
        """
