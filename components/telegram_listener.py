"""
Component 1 – Telegram Listener

Connects to configured channels via Telethon, forwards raw messages onto an
asyncio queue. Contains NO analysis logic.
"""
import asyncio
from datetime import datetime
from typing import Optional

from telethon import TelegramClient, events

from config import config
from utils.logger import get_logger

log = get_logger(__name__)


class RawMessage:
    __slots__ = ("text", "channel", "timestamp", "message_id", "urls")

    def __init__(self, text: str, channel: str, timestamp: datetime, message_id: int, urls: list[str] | None = None):
        self.text = text
        self.channel = channel
        self.timestamp = timestamp
        self.message_id = message_id
        self.urls: list[str] = urls or []


class TelegramListener:
    """
    Listens to one or more Telegram channels and puts RawMessage objects onto
    the provided asyncio queue.

    After connecting, sets client_ready and populates client_ref[0] so that
    other components (e.g. TelegramTrendSource) can reuse the same connection.
    """

    def __init__(
        self,
        queue: asyncio.Queue,
        client_ready: asyncio.Event,
        client_ref: list,
    ) -> None:
        self._queue = queue
        self._client: Optional[TelegramClient] = None
        self._running = False
        self._client_ready = client_ready
        self._client_ref = client_ref

    async def start(self) -> None:
        if not config.TELEGRAM_API_ID or not config.TELEGRAM_API_HASH:
            log.warning(
                "Telegram credentials not configured — listener disabled. "
                "Set TELEGRAM_API_ID and TELEGRAM_API_HASH in .configuration"
            )
            return

        if not config.TELEGRAM_CHANNELS:
            log.warning("No TELEGRAM_CHANNELS configured — listener disabled.")
            return

        self._client = TelegramClient(
            config.TELEGRAM_SESSION_NAME,
            config.TELEGRAM_API_ID,
            config.TELEGRAM_API_HASH,
        )

        await self._client.start(phone=config.TELEGRAM_PHONE or None)
        self._client_ref[0] = self._client
        self._client_ready.set()
        log.info("Telegram client connected")

        # Resolve channel entities once so Telethon can match them in events
        entities = []
        for ch in config.TELEGRAM_CHANNELS:
            try:
                entity = await self._client.get_entity(ch)
                entities.append(entity)
                log.info("Subscribed to channel: %s", ch)
            except Exception as exc:
                log.error("Could not resolve channel %s: %s", ch, exc)

        if not entities:
            log.error("No channels resolved — listener inactive.")
            return

        @self._client.on(events.NewMessage(chats=entities))
        async def _on_message(event):
            text = event.message.message or ""
            if not text.strip():
                return
            # Extract all hyperlink URLs from message entities
            urls: list[str] = []
            for ent in (event.message.entities or []):
                if hasattr(ent, "url") and ent.url:
                    urls.append(ent.url)
                elif hasattr(ent, "offset") and hasattr(ent, "length") and not hasattr(ent, "url"):
                    # Plain URL entity — text slice is the URL
                    urls.append(text[ent.offset: ent.offset + ent.length])
            raw = RawMessage(
                text=text,
                channel=getattr(event.chat, "username", str(event.chat_id)),
                timestamp=event.message.date,
                message_id=event.message.id,
                urls=urls,
            )
            await self._queue.put(raw)
            log.debug(
                "Queued message id=%d from %s (len=%d)",
                raw.message_id,
                raw.channel,
                len(raw.text),
            )

        self._running = True
        log.info(
            "Telegram listener active on %d channel(s)", len(entities)
        )
        await self._client.run_until_disconnected()

    async def stop(self) -> None:
        self._running = False
        if self._client and self._client.is_connected():
            await self._client.disconnect()
            log.info("Telegram client disconnected")
