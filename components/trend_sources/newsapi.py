"""
NewsAPI trend source. Fetches top headlines.
"""
import ssl

import aiohttp
import certifi

from components.trend_sources.base import TrendSource
from utils.keywords import extract_keywords
from utils.logger import get_logger

log = get_logger(__name__)

_ssl_context = ssl.create_default_context(cafile=certifi.where())


class NewsAPISource(TrendSource):
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    @property
    def name(self) -> str:
        return "NewsAPI"

    async def fetch(self) -> list[dict]:
        if not self._api_key:
            return []
        url = "https://newsapi.org/v2/top-headlines"
        params = {"apiKey": self._api_key, "language": "en", "pageSize": 40}
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15),
                connector=aiohttp.TCPConnector(ssl=_ssl_context),
            ) as session:
                async with session.get(url, params=params) as resp:
                    data = await resp.json()
        except Exception as exc:
            log.warning("NewsAPI fetch failed: %s", exc)
            return []

        results = []
        for art in data.get("articles", []):
            title = art.get("title", "")
            desc = art.get("description", "") or ""
            results.append({
                "title": title,
                "source": art.get("source", {}).get("name", "newsapi"),
                "keywords": extract_keywords(f"{title} {desc}"),
            })
        return results
