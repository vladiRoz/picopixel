"""
Component 4 – Global Trend Collector

Periodically fetches trending topics from NewsAPI and RSS feeds.
Stores extracted keywords in the database.
Runs as an independent background task.
"""
import asyncio
import re
import ssl
from typing import Optional

import aiohttp
import certifi
import feedparser

_ssl_context = ssl.create_default_context(cafile=certifi.where())

from config import config
from storage.store import Store
from utils.logger import get_logger

log = get_logger(__name__)

# Common stop-words to exclude from keywords
_STOP = {
    "the", "a", "an", "in", "on", "at", "to", "for", "of", "and", "or",
    "is", "are", "was", "were", "be", "been", "has", "have", "had",
    "it", "its", "by", "as", "with", "from", "that", "this", "but",
    "not", "what", "how", "who", "which", "will", "can", "may", "new",
    "says", "said", "after", "over", "more", "than", "up", "down",
}

_WORD_RE = re.compile(r"[A-Za-z]{3,}")


def _extract_keywords(text: str) -> list[str]:
    words = _WORD_RE.findall(text.lower())
    seen = set()
    result = []
    for w in words:
        if w not in _STOP and w not in seen:
            seen.add(w)
            result.append(w)
    return result[:15]


class TrendCollector:
    def __init__(self, store: Store) -> None:
        self._store = store

    async def run(self) -> None:
        log.info("TrendCollector started (interval=%ds)", config.NEWS_REFRESH_INTERVAL)
        while True:
            try:
                await self._collect()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("TrendCollector error: %s", exc, exc_info=True)
            await asyncio.sleep(config.NEWS_REFRESH_INTERVAL)

    async def _collect(self) -> None:
        trends: list[dict] = []
        trends.extend(await self._fetch_rss())
        if config.NEWS_API_KEY:
            trends.extend(await self._fetch_newsapi())
        if trends:
            self._store.save_trends(trends)
            log.info("TrendCollector: saved %d trend items", len(trends))
        else:
            log.warning("TrendCollector: no trends collected")

    # ------------------------------------------------------------------
    # RSS
    # ------------------------------------------------------------------

    async def _fetch_rss(self) -> list[dict]:
        results = []
        for url in config.RSS_FEEDS:
            try:
                items = await self._parse_rss(url)
                results.extend(items)
            except Exception as exc:
                log.warning("RSS fetch failed for %s: %s", url, exc)
        return results

    async def _parse_rss(self, url: str) -> list[dict]:
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
            combined = f"{title} {summary}"
            items.append({
                "title": title,
                "source": url,
                "keywords": _extract_keywords(combined),
            })
        return items

    # ------------------------------------------------------------------
    # NewsAPI
    # ------------------------------------------------------------------

    async def _fetch_newsapi(self) -> list[dict]:
        url = "https://newsapi.org/v2/top-headlines"
        params = {
            "apiKey": config.NEWS_API_KEY,
            "language": "en",
            "pageSize": 40,
        }
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15)
            ) as session:
                async with session.get(url, params=params) as resp:
                    data = await resp.json()
        except Exception as exc:
            log.warning("NewsAPI request failed: %s", exc)
            return []

        articles = data.get("articles", [])
        results = []
        for art in articles:
            title = art.get("title", "")
            desc = art.get("description", "") or ""
            combined = f"{title} {desc}"
            results.append({
                "title": title,
                "source": art.get("source", {}).get("name", "newsapi"),
                "keywords": _extract_keywords(combined),
            })
        return results
