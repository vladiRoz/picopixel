"""
Telegram channel trend source.

Reuses the shared TelegramClient from TelegramListener — waits for the
client to be ready before fetching, so no second connection is needed.

Tracks the last seen message ID per channel so each fetch only reads
new messages since the previous run.
"""
import asyncio

from components.trend_sources.base import TrendSource
from utils.keywords import extract_keywords
from utils.logger import get_logger

log = get_logger(__name__)

# On the very first fetch (no last_id yet), load this many messages as a baseline
_INITIAL_LOAD = 30


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
        # {channel: last_message_id} — persists in memory across fetches
        self._last_ids: dict[str, int] = {}

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
                new_items, new_last_id = await self._fetch_channel(client, channel)
                results.extend(new_items)
                if new_last_id:
                    self._last_ids[channel] = new_last_id
            except Exception as exc:
                log.warning("TelegramTrendSource: failed to fetch from %s: %s", channel, exc)

        return results

    async def _fetch_channel(self, client, channel: str) -> tuple[list[dict], int]:
        last_id = self._last_ids.get(channel)

        if last_id is None:
            # First run — load baseline messages, don't pass min_id
            messages = await client.get_messages(channel, limit=_INITIAL_LOAD)
        else:
            # Only fetch messages newer than the last one we saw
            messages = await client.get_messages(channel, min_id=last_id, limit=200)

        if not messages:
            log.debug("TelegramTrendSource: no new messages from %s", channel)
            return [], last_id

        log.debug(
            "TelegramTrendSource: %d new message(s) from %s (min_id=%s)",
            len(messages), channel, last_id,
        )

        results = []
        max_id = last_id or 0
        for msg in messages:
            text = getattr(msg, "message", "") or ""
            if not text.strip():
                continue
            results.append({
                "title": text[:120].replace("\n", " "),
                "source": f"telegram:{channel}",
                "keywords": extract_keywords(text),
            })
            if msg.id > max_id:
                max_id = msg.id

        return results, max_id
