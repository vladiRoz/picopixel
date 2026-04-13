"""
RSS feed trend source. Fetches and parses one or more RSS URLs.
"""
import ssl

import aiohttp
import certifi
import feedparser

from components.trend_sources.base import TrendSource
from utils.keywords import extract_keywords
from utils.logger import get_logger

log = get_logger(__name__)

_ssl_context = ssl.create_default_context(cafile=certifi.where())


class RSSSource(TrendSource):
    def __init__(self, urls: list[str]) -> None:
        self._urls = urls

    @property
    def name(self) -> str:
        return "RSS"

    async def fetch(self) -> list[dict]:
        results = []
        for url in self._urls:
            try:
                results.extend(await self._parse(url))
            except Exception as exc:
                log.warning("RSS fetch failed for %s: %s", url, exc)
        return results

    async def _parse(self, url: str) -> list[dict]:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=15),
            connector=aiohttp.TCPConnector(ssl=_ssl_context),
        ) as session:
            async with session.get(url) as resp:
                content = await resp.read()

        feed = feedparser.parse(content)
        items = []
        for entry in feed.entries[:20]:
            title = getattr(entry, "title", "")
            summary = getattr(entry, "summary", "")
            items.append({
                "title": title,
                "source": url,
                "keywords": extract_keywords(f"{title} {summary}"),
            })
        return items
