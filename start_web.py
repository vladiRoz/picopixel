"""
Starts only the web admin server (no Telegram, no LLM).
Useful for previewing the UI and testing feedback before running the full system.

Usage:
    python start_web.py
"""
import asyncio
import sys
from pathlib import Path

from config import config
from storage.store import Store
from utils.logger import get_logger
from components.meta_mapping import MetaMap
import asyncio as _asyncio
from components.meta_discovery import MetaDiscovery
from components.feedback_server import FeedbackServer

log = get_logger(__name__)


async def main() -> None:
    Path(config.STORAGE_DIR).mkdir(parents=True, exist_ok=True)
    store = Store(config.DB_PATH)
    meta_map = MetaMap(store)
    broadcast_queue: asyncio.Queue = asyncio.Queue()
    meta_discovery = MetaDiscovery(asyncio.Queue(), meta_map, store, broadcast_queue)
    server = FeedbackServer(store, meta_map, meta_discovery)
    log.info("Web admin → http://localhost:%d", config.FEEDBACK_PORT)
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())
