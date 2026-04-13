"""
Telegram channel trend source.

Reuses the shared TelegramClient from TelegramListener — waits for the
client to be ready before fetching, so no second connection is needed.
"""
import asyncio

from components.trend_sources.base import TrendSource
from utils.keywords import extract_keywords
from utils.logger import get_logger

log = get_logger(__name__)

# How many recent messages to pull per channel per refresh
_MESSAGES_PER_CHANNEL = 30


class TelegramTrendSource(TrendSource):
    def __init__(self, channels: list[str], client_ready: asyncio.Event, client_ref: list) -> None:
        """
        channels     – list of channel usernames or IDs to monitor for trends
        client_ready – Event that gets set once the TelegramListener has connected
        client_ref   – Single-element list holding the TelegramClient instance.
                       List is used so the reference can be set after construction.
        """
        self._channels = channels
        self._client_ready = client_ready
        self._client_ref = client_ref

    @property
    def name(self) -> str:
        return "Telegram"

    async def fetch(self) -> list[dict]:
        if not self._channels:
            return []

        # Wait up to 60s for the Telegram client to connect
        try:
            await asyncio.wait_for(self._client_ready.wait(), timeout=60)
        except asyncio.TimeoutError:
            log.warning("TelegramTrendSource: client not ready after 60s, skipping fetch")
            return []

        client = self._client_ref[0]
        if client is None:
            return []

        results = []
        for channel in self._channels:
            try:
                messages = await client.get_messages(channel, limit=_MESSAGES_PER_CHANNEL)
                for msg in messages:
                    text = getattr(msg, "message", "") or ""
                    if not text.strip():
                        continue
                    results.append({
                        "title": text[:120].replace("\n", " "),
                        "source": f"telegram:{channel}",
                        "keywords": extract_keywords(text),
                    })
                log.debug(
                    "TelegramTrendSource: fetched %d messages from %s",
                    len(messages), channel,
                )
            except Exception as exc:
                log.warning("TelegramTrendSource: failed to fetch from %s: %s", channel, exc)

        return results
