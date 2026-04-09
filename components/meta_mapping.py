"""
Component 5 – Meta Mapping System

Maintains the dynamic map of coins → metas → global trends.
Loaded from and persisted to the database. Provides query interface
used by other components.
"""
import re
from datetime import datetime
from typing import Optional

from models.meta import Meta
from storage.store import Store
from utils.logger import get_logger

log = get_logger(__name__)


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


class MetaMap:
    """
    In-memory meta registry backed by SQLite.
    Thread-safe reads; writes should be called from a single async task.
    """

    def __init__(self, store: Store) -> None:
        self._store = store
        self._metas: dict[str, Meta] = {}
        self._load()

    def _load(self) -> None:
        for meta in self._store.get_all_metas():
            self._metas[meta.id] = meta
        log.info("MetaMap loaded %d metas", len(self._metas))

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def add_coin_to_meta(self, meta_id: str, symbol: str) -> None:
        meta = self._metas.get(meta_id)
        if not meta:
            return
        symbol = symbol.upper()
        if symbol not in meta.coins:
            meta.coins.append(symbol)
            meta.updated_at = datetime.utcnow()
            self._store.save_meta(meta)

    def upsert_meta(self, meta: Meta) -> None:
        existing = self._metas.get(meta.id)
        if existing:
            # Merge coins list
            for c in meta.coins:
                if c not in existing.coins:
                    existing.coins.append(c)
            existing.strength = meta.strength
            existing.trend_alignment = meta.trend_alignment
            existing.updated_at = datetime.utcnow()
            self._store.save_meta(existing)
        else:
            self._metas[meta.id] = meta
            self._store.save_meta(meta)
            log.info("MetaMap: new meta registered: %s", meta.name)

    def update_trend_alignment(self, meta_id: str, alignment: float) -> None:
        meta = self._metas.get(meta_id)
        if meta:
            meta.trend_alignment = max(0.0, min(1.0, alignment))
            meta.updated_at = datetime.utcnow()
            self._store.save_meta(meta)

    def update_strength(self, meta_id: str, strength: float) -> None:
        meta = self._metas.get(meta_id)
        if meta:
            meta.strength = max(0.0, min(1.0, strength))
            meta.updated_at = datetime.utcnow()
            self._store.save_meta(meta)

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_meta(self, meta_id: str) -> Optional[Meta]:
        return self._metas.get(meta_id)

    def get_all(self) -> list[Meta]:
        return sorted(self._metas.values(), key=lambda m: m.strength, reverse=True)

    def find_or_create(self, name: str) -> Meta:
        slug = _slugify(name)
        if slug in self._metas:
            return self._metas[slug]
        meta = Meta(
            id=slug,
            name=name,
            description=f"Auto-discovered meta: {name}",
            keywords=[w for w in name.lower().split() if len(w) > 2],
            is_emerging=True,
        )
        self.upsert_meta(meta)
        return meta

    def get_metas_for_coin(self, symbol: str) -> list[Meta]:
        symbol = symbol.upper()
        return [m for m in self._metas.values() if symbol in m.coins]

    def correlate_with_trends(self, trend_keywords: list[str]) -> dict[str, float]:
        """
        Return {meta_id: alignment_score} based on keyword overlap with global trends.
        """
        trend_set = set(k.lower() for k in trend_keywords)
        scores: dict[str, float] = {}
        for meta_id, meta in self._metas.items():
            meta_kw = set(k.lower() for k in meta.keywords)
            overlap = len(meta_kw & trend_set)
            if meta_kw:
                scores[meta_id] = min(1.0, overlap / len(meta_kw))
            else:
                scores[meta_id] = 0.0
        return scores
