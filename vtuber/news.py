import asyncio
import logging
import time
from dataclasses import dataclass, field

import aiohttp
import feedparser

logger = logging.getLogger(__name__)

DEFAULT_FEEDS = [
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
    "https://feeds.reuters.com/reuters/topNews",
    "https://feeds.npr.org/1001/rss.xml",
    "https://www.reddit.com/r/worldnews/.rss",
]


@dataclass
class NewsItem:
    title: str
    summary: str
    link: str
    source: str
    published: str = ""


@dataclass
class NewsFetcher:
    feeds: list[str] = field(default_factory=lambda: list(DEFAULT_FEEDS))
    _cache: list[NewsItem] = field(default_factory=list, repr=False)
    _last_fetch: float = 0.0
    cache_ttl: int = 300  # 5 minutes

    async def fetch(self, max_items: int = 20) -> list[NewsItem]:
        if self._cache and (time.time() - self._last_fetch) < self.cache_ttl:
            return self._cache[:max_items]

        items: list[NewsItem] = []
        async with aiohttp.ClientSession() as session:
            tasks = [self._fetch_feed(session, url) for url in self.feeds]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, list):
                items.extend(result)
            elif isinstance(result, Exception):
                logger.warning("Feed fetch failed: %s", result)

        self._cache = items
        self._last_fetch = time.time()
        return items[:max_items]

    async def _fetch_feed(self, session: aiohttp.ClientSession, url: str) -> list[NewsItem]:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                text = await resp.text()
        except Exception as e:
            logger.warning("Failed to fetch %s: %s", url, e)
            return []

        feed = await asyncio.to_thread(feedparser.parse, text)
        source = feed.feed.get("title", url)
        items = []
        for entry in feed.entries[:10]:
            items.append(NewsItem(
                title=entry.get("title", ""),
                summary=entry.get("summary", "")[:500],
                link=entry.get("link", ""),
                source=source,
                published=entry.get("published", ""),
            ))
        return items

    async def get_topics_summary(self, max_items: int = 10) -> str:
        items = await self.fetch(max_items)
        if not items:
            return "No current news available."
        lines = []
        for i, item in enumerate(items, 1):
            lines.append(f"{i}. [{item.source}] {item.title}")
            if item.summary:
                clean = item.summary.replace("<p>", "").replace("</p>", "").strip()
                lines.append(f"   {clean[:200]}")
        return "\n".join(lines)
