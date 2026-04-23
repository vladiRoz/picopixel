# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the System

**Full system** (Telegram + LLM + web admin):
```bash
source .venv/bin/activate
python3 main.py
```

**Web admin only** (no Telegram, no LLM — for UI testing):
```bash
python3 start_web.py
```

Web admin runs at `http://0.0.0.0:8080` by default.

**Configuration** lives in `.configuration` (dotenv format). Required keys: `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `OPENROUTER_API_KEY`. On first run with Telegram credentials, Telethon will prompt for phone + 2FA and save a session file.

**Syntax checking** (no test suite exists):
```bash
python3 -m py_compile <file.py>
```

**Dependency install** (on device, no venv module):
```bash
pip install -r requirements.txt --break-system-packages
```

## Architecture

### Async pipeline (single process, all components run as `asyncio.Task`s)

```
TelegramListener
    │ raw_queue (RawMessage with .text + .urls extracted from entities)
    ▼
MessageParser
    ├─► perf_queue ──► PerformanceLearner   (PERF_RESULT / PERF_SUMMARY only)
    └─► parsed_queue
            │
            ▼
    MetaAnalysisEngine  (LLM via OpenRouter → assigns 1–3 meta labels)
            │ analysis_queue: (signal, metas)
            ▼
    MetaDiscovery  (registers new metas, records co-occurrences, broadcasts)
            │ broadcast_queue: (signal, metas, meta_ids)
            ▼
    EvaluationEngine  (scores whale/momentum/meta; LLM recommendation → SQLite)

Parallel:
  TrendCollector      → RSS + NewsAPI + Telegram trend channels → SQLite
  AdaptationMonitor   → periodic meta strength recalculation
  FeedbackServer      → FastAPI web UI on port 8080
```

### Message parsing strategy

`MessageParser` is regex-first, LLM-fallback. Ticker resolution priority:
1. **GeckoTerminal API** — pool address extracted from hyperlink entities in the Telegram message, resolved via `api.geckoterminal.com/api/v2/networks/solana/pools/{address}`. Numeric-only results (e.g. `33 / SOL`) are rejected.
2. **Dev line** — `🛠️ Dev: X SOL | Y% $TICKER`
3. **First letter-starting `$TICKER`** in message text
4. **Coin name** from message header (uppercased, spaces removed)

Invisible unicode (U+200E LTR marks) is stripped from coin names via `_strip_invis()`.

Event types: `WHALE_BUY`, `ANOTHER_WHALE`, `ACCUMULATION`, `ENTRY_SIGNAL`, `GAIN_UPDATE`, `SUMMARY`, `PERF_RESULT` (📈 NX multiplier), `PERF_SUMMARY` (🏆 leaderboard), `UNKNOWN`.

### Storage (SQLite via `storage/store.py`)

Tables: `coin_signals`, `metas`, `evaluations`, `feedback`, `trends`, `performance_outcomes`, `meta_cooccurrence`.

`MetaMap` is an in-memory dict (`{meta_id: Meta}`) backed by SQLite, loaded at startup. After an Admin reset (`/admin/reset`), both the DB and in-memory map are cleared.

### Learning loop

- **AdaptationMonitor** recalculates meta `strength` every 600s from coin activity + gain data.
- **PerformanceLearner** processes `PERF_RESULT`/`PERF_SUMMARY` messages: looks up the prior evaluation for each coin, judges the prediction (correct/wrong/missed), adjusts meta strength (±0.02–0.08), saves to `performance_outcomes`.
- **Meta co-occurrence**: every time a coin gets ≥2 metas, all pairs are recorded in `meta_cooccurrence`. When results arrive, win count and avg gain_x are updated. The LLM prompt includes the top co-occurrence combos so it can recognise coins that combine proven meta pairs (e.g. `Politics/Trump + Culture/GenZ`).

### Web admin tabs

| Tab | Route | Purpose |
|-----|-------|---------|
| Dashboard | `/` | Stats + recent evaluations with source label |
| Evaluations | `/evaluations` | Full table; Source column shows "Solana Early" or "Whale" |
| Metas | `/metas` | Registry with strength/trend alignment |
| Trends | `/trends` | Collected RSS/news/Telegram trends |
| Feedback | `/feedback` | Manual meta correction form |
| Admin | `/admin` | Database reset (confirmation modal required) |

Templates are inline Jinja2 strings in `feedback_server.py` — no separate template files.

## Key Config Values

| Key | Default | Notes |
|-----|---------|-------|
| `TELEGRAM_CHANNELS` | — | Comma-separated channel usernames |
| `TREND_TELEGRAM_CHANNELS` | — | Separate channels for trend collection |
| `OPENROUTER_MODEL` | `openai/gpt-4o-mini` | Used for meta assignment + evaluation |
| `FEEDBACK_SERVER_PORT` | `8080` | Web admin port |
| `ADAPTATION_MONITOR_INTERVAL_SECONDS` | `600` | Meta strength recalc interval |
| `STORAGE_DIR` / `DB_PATH` | `./data` / `./data/meta.db` | SQLite location |
