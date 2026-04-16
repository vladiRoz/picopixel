"""
Entry point – orchestrates all components and manages graceful shutdown.

Usage:
    python main.py

On first run Telethon will prompt for your phone number and 2FA code.
Subsequent runs use the saved session file.
"""
import asyncio
import signal
import sys
from pathlib import Path

from config import config
from storage.store import Store
from utils.logger import get_logger
from components.telegram_listener import TelegramListener
from components.message_parser import MessageParser
from components.meta_analysis import MetaAnalysisEngine
from components.trend_collector import TrendCollector
from components.trend_sources import RSSSource, NewsAPISource, TelegramTrendSource
from components.meta_mapping import MetaMap
from components.meta_discovery import MetaDiscovery
from components.adaptation_monitor import AdaptationMonitor
from components.evaluation_engine import EvaluationEngine
from components.feedback_server import FeedbackServer
from components.performance_learner import PerformanceLearner

log = get_logger(__name__)


async def main() -> None:
    # ------------------------------------------------------------------
    # Validate configuration
    # ------------------------------------------------------------------
    missing = config.validate()
    if missing:
        log.error(
            "Missing required configuration: %s\n"
            "Edit .configuration and fill in the required values.",
            ", ".join(missing),
        )
        sys.exit(1)

    # Ensure data directory exists
    Path(config.STORAGE_DIR).mkdir(parents=True, exist_ok=True)

    log.info("Starting Meta Coin Analysis System")
    log.info("Storage: %s", config.DB_PATH)
    log.info("Channels: %s", config.TELEGRAM_CHANNELS)

    # ------------------------------------------------------------------
    # Shared infrastructure
    # ------------------------------------------------------------------
    store = Store(config.DB_PATH)
    meta_map = MetaMap(store)

    # Async queues for inter-component messaging
    raw_queue: asyncio.Queue = asyncio.Queue(maxsize=500)
    parsed_queue: asyncio.Queue = asyncio.Queue(maxsize=500)
    analysis_queue: asyncio.Queue = asyncio.Queue(maxsize=500)
    broadcast_queue: asyncio.Queue = asyncio.Queue(maxsize=500)
    perf_queue: asyncio.Queue = asyncio.Queue(maxsize=200)

    # Shared Telegram client handle (set by TelegramListener once connected)
    telegram_client_ready: asyncio.Event = asyncio.Event()
    telegram_client_ref: list = [None]

    # ------------------------------------------------------------------
    # Component instances
    # ------------------------------------------------------------------
    listener = TelegramListener(raw_queue, telegram_client_ready, telegram_client_ref)
    parser = MessageParser(raw_queue, parsed_queue, store, perf_queue=perf_queue)
    meta_engine = MetaAnalysisEngine(parsed_queue, analysis_queue, store)

    trend_sources = [
        RSSSource(config.RSS_FEEDS),
        NewsAPISource(config.NEWS_API_KEY),
        TelegramTrendSource(config.TREND_TELEGRAM_CHANNELS, telegram_client_ready, telegram_client_ref),
    ]
    trend_collector = TrendCollector(trend_sources, store)
    meta_discovery = MetaDiscovery(analysis_queue, meta_map, store, broadcast_queue)
    adaptation_monitor = AdaptationMonitor(meta_map, store, config.ADAPTATION_INTERVAL)
    evaluation_engine = EvaluationEngine(broadcast_queue, meta_map, store)
    performance_learner = PerformanceLearner(perf_queue, meta_map, store)
    feedback_server = FeedbackServer(store, meta_map, meta_discovery)

    # ------------------------------------------------------------------
    # Launch all tasks
    # ------------------------------------------------------------------
    tasks = [
        asyncio.create_task(parser.run(),             name="message_parser"),
        asyncio.create_task(meta_engine.run(),        name="meta_analysis"),
        asyncio.create_task(trend_collector.run(),    name="trend_collector"),
        asyncio.create_task(meta_discovery.run(),     name="meta_discovery"),
        asyncio.create_task(adaptation_monitor.run(), name="adaptation_monitor"),
        asyncio.create_task(evaluation_engine.run(),    name="evaluation_engine"),
        asyncio.create_task(performance_learner.run(), name="performance_learner"),
        asyncio.create_task(feedback_server.run(),     name="feedback_server"),
    ]

    # Telegram listener is a long-running coroutine (not a standard loop task)
    listener_task = asyncio.create_task(listener.start(), name="telegram_listener")
    tasks.append(listener_task)

    log.info("All components started. Web admin: http://localhost:%d", config.FEEDBACK_PORT)

    # ------------------------------------------------------------------
    # Graceful shutdown on SIGINT / SIGTERM
    # ------------------------------------------------------------------
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def _shutdown(sig_name: str) -> None:
        log.info("Received %s — initiating shutdown", sig_name)
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _shutdown, sig.name)

    # Wait until shutdown is requested
    await shutdown_event.wait()

    log.info("Cancelling tasks…")
    for t in tasks:
        t.cancel()

    await asyncio.gather(*tasks, return_exceptions=True)
    await listener.stop()
    log.info("Shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
