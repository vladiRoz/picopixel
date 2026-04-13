"""
SQLite-backed persistence for coin signals, metas, evaluations, and feedback.
All methods are synchronous (called from async code via run_in_executor if needed,
but SQLite on mobile is fast enough for our write volume).
"""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from models.coin import CoinSignal, EventType
from models.meta import Meta, CoinEvaluation, Recommendation
from utils.logger import get_logger

log = get_logger(__name__)


class Store:
    def __init__(self, db_path: str) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        self._init_schema()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS coin_signals (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol      TEXT NOT NULL,
                    coin_name   TEXT NOT NULL,
                    event_type  TEXT NOT NULL,
                    channel     TEXT NOT NULL,
                    market_cap  REAL,
                    volume_1h   REAL,
                    liquidity   REAL,
                    holders     INTEGER,
                    gain_pct    REAL,
                    raw_message TEXT,
                    payload     TEXT NOT NULL,
                    timestamp   TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS metas (
                    id              TEXT PRIMARY KEY,
                    name            TEXT NOT NULL,
                    description     TEXT,
                    keywords        TEXT,
                    strength        REAL DEFAULT 0.5,
                    trend_alignment REAL DEFAULT 0.0,
                    coins           TEXT,
                    is_emerging     INTEGER DEFAULT 0,
                    created_at      TEXT NOT NULL,
                    updated_at      TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS evaluations (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    coin_symbol     TEXT NOT NULL,
                    coin_name       TEXT NOT NULL,
                    metas           TEXT,
                    overall_score   REAL,
                    recommendation  TEXT,
                    reasoning       TEXT,
                    payload         TEXT NOT NULL,
                    timestamp       TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS feedback (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    coin_symbol TEXT NOT NULL,
                    old_metas   TEXT,
                    new_metas   TEXT,
                    note        TEXT,
                    timestamp   TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS trends (
                    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                    title              TEXT NOT NULL,
                    source             TEXT,
                    keywords           TEXT,
                    timestamp          TEXT NOT NULL,
                    original_timestamp TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_signals_symbol ON coin_signals(symbol);
            """)
            # Migration: add original_timestamp column if it doesn't exist yet
            cols = [r[1] for r in conn.execute("PRAGMA table_info(trends)").fetchall()]
            if "original_timestamp" not in cols:
                conn.execute("ALTER TABLE trends ADD COLUMN original_timestamp TEXT")
            conn.executescript("""
                CREATE INDEX IF NOT EXISTS idx_signals_ts     ON coin_signals(timestamp);
                CREATE INDEX IF NOT EXISTS idx_evals_symbol   ON evaluations(coin_symbol);
                CREATE INDEX IF NOT EXISTS idx_evals_ts       ON evaluations(timestamp);
            """)
        log.debug("Schema initialised at %s", self._db_path)

    # ------------------------------------------------------------------
    # Coin signals
    # ------------------------------------------------------------------

    def save_signal(self, signal: CoinSignal) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO coin_signals
                   (symbol, coin_name, event_type, channel, market_cap,
                    volume_1h, liquidity, holders, gain_pct, raw_message,
                    payload, timestamp)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    signal.symbol,
                    signal.coin_name,
                    signal.event_type.value,
                    signal.channel,
                    signal.market_cap,
                    signal.volume_1h,
                    signal.liquidity,
                    signal.holders,
                    signal.gain_percentage,
                    signal.raw_message[:2000],
                    json.dumps(signal.to_dict()),
                    signal.timestamp.isoformat(),
                ),
            )

    def get_recent_signals(self, limit: int = 50) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT payload FROM coin_signals ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [json.loads(r["payload"]) for r in rows]

    def get_signals_for_symbol(self, symbol: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT payload FROM coin_signals WHERE symbol=? ORDER BY timestamp DESC LIMIT 20",
                (symbol.upper(),),
            ).fetchall()
        return [json.loads(r["payload"]) for r in rows]

    # ------------------------------------------------------------------
    # Metas
    # ------------------------------------------------------------------

    def save_meta(self, meta: Meta) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO metas
                   (id, name, description, keywords, strength, trend_alignment,
                    coins, is_emerging, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    meta.id,
                    meta.name,
                    meta.description,
                    json.dumps(meta.keywords),
                    meta.strength,
                    meta.trend_alignment,
                    json.dumps(meta.coins),
                    int(meta.is_emerging),
                    meta.created_at.isoformat(),
                    meta.updated_at.isoformat(),
                ),
            )

    def get_meta(self, meta_id: str) -> Optional[Meta]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM metas WHERE id=?", (meta_id,)
            ).fetchone()
        if not row:
            return None
        return self._row_to_meta(row)

    def get_all_metas(self) -> list[Meta]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM metas ORDER BY strength DESC"
            ).fetchall()
        return [self._row_to_meta(r) for r in rows]

    def _row_to_meta(self, row) -> Meta:
        return Meta(
            id=row["id"],
            name=row["name"],
            description=row["description"] or "",
            keywords=json.loads(row["keywords"] or "[]"),
            strength=row["strength"],
            trend_alignment=row["trend_alignment"],
            coins=json.loads(row["coins"] or "[]"),
            is_emerging=bool(row["is_emerging"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    # ------------------------------------------------------------------
    # Evaluations
    # ------------------------------------------------------------------

    def save_evaluation(self, ev: CoinEvaluation) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO evaluations
                   (coin_symbol, coin_name, metas, overall_score,
                    recommendation, reasoning, payload, timestamp)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    ev.coin_symbol,
                    ev.coin_name,
                    json.dumps(ev.metas),
                    ev.overall_score,
                    ev.recommendation.value,
                    ev.reasoning,
                    json.dumps(ev.to_dict()),
                    ev.timestamp.isoformat(),
                ),
            )

    def get_recent_evaluations(self, limit: int = 50) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT payload FROM evaluations ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [json.loads(r["payload"]) for r in rows]

    # ------------------------------------------------------------------
    # Feedback
    # ------------------------------------------------------------------

    def save_feedback(
        self,
        coin_symbol: str,
        old_metas: list[str],
        new_metas: list[str],
        note: str = "",
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO feedback (coin_symbol, old_metas, new_metas, note, timestamp)
                   VALUES (?,?,?,?,?)""",
                (
                    coin_symbol.upper(),
                    json.dumps(old_metas),
                    json.dumps(new_metas),
                    note,
                    datetime.utcnow().isoformat(),
                ),
            )

    def get_recent_feedback(self, limit: int = 50) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM feedback ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Trends
    # ------------------------------------------------------------------

    def save_trends(self, trends: list[dict]) -> None:
        """Append new trends — history is kept and cleaned up monthly."""
        now = datetime.utcnow().isoformat()
        with self._conn() as conn:
            conn.executemany(
                "INSERT INTO trends (title, source, keywords, timestamp, original_timestamp) VALUES (?,?,?,?,?)",
                [
                    (
                        t.get("title", ""),
                        t.get("source", ""),
                        json.dumps(t.get("keywords", [])),
                        now,
                        t.get("original_timestamp"),
                    )
                    for t in trends
                ],
            )

    def cleanup_old_trends(self) -> int:
        """Delete trends older than 30 days. Returns number of rows deleted."""
        cutoff = (datetime.utcnow() - timedelta(days=30)).isoformat()
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM trends WHERE timestamp < ?", (cutoff,))
            return cur.rowcount

    def get_trends(self, hours: int = 24) -> list[dict]:
        """Return trends from the last `hours` hours for scoring."""
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT title, source, keywords FROM trends WHERE timestamp >= ? ORDER BY timestamp DESC",
                (cutoff,),
            ).fetchall()
        return [
            {
                "title": r["title"],
                "source": r["source"],
                "keywords": json.loads(r["keywords"] or "[]"),
            }
            for r in rows
        ]

    def get_trends_for_display(self, limit: int = 200, source_filter: str = "") -> list[dict]:
        """Return trends with timestamps for the web admin, optionally filtered by source."""
        with self._conn() as conn:
            if source_filter:
                rows = conn.execute(
                    "SELECT title, source, keywords, timestamp FROM trends "
                    "WHERE source LIKE ? ORDER BY timestamp DESC LIMIT ?",
                    (f"%{source_filter}%", limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT title, source, keywords, timestamp FROM trends "
                    "ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [
            {
                "title": r["title"],
                "source": r["source"],
                "keywords": json.loads(r["keywords"] or "[]"),
                "timestamp": r["timestamp"],
                "original_timestamp": r["original_timestamp"],
            }
            for r in rows
        ]

    def get_trend_sources(self) -> list[str]:
        """Return distinct source values for filter UI."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT source FROM trends ORDER BY source"
            ).fetchall()
        return [r["source"] for r in rows]

    def get_trend_stats(self) -> dict:
        """Return summary stats for the trends dashboard."""
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) as c FROM trends").fetchone()["c"]
            last_row = conn.execute(
                "SELECT timestamp FROM trends ORDER BY timestamp DESC LIMIT 1"
            ).fetchone()
            source_count = conn.execute(
                "SELECT COUNT(DISTINCT source) as c FROM trends"
            ).fetchone()["c"]
        return {
            "total": total,
            "last_collected": last_row["timestamp"][:19] if last_row else "Never",
            "source_count": source_count,
        }
