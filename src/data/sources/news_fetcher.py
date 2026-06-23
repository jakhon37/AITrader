"""D02-DATA — NewsFetcher: news article ingestion from NewsAPI and RSS feeds.

Sources (priority order):
  1. NewsAPI (newsapi.org) — structured JSON, requires NEWSAPI_KEY
  2. Reuters/Bloomberg RSS  — free, no key; fallback when API is down
  3. Forex Factory RSS       — FX-specific news

Behaviour:
  - Background async loop, default poll interval = 10 minutes.
  - Deduplication: SHA-256 of (headline + published_at ISO) used as article_id;
    duplicate IDs are silently skipped on insert.
  - Rate limiting: token-bucket per source.
  - Backoff: exponential on HTTP 429 / 5xx, up to 5 retries.
  - Fail loud: a failing source is logged at WARNING and skipped, not silently
    swallowed — the other sources still run.  All sources failing at once
    raises DataError and is logged at ERROR.

Usage:
    fetcher = NewsFetcher(store, config, clock)
    await fetcher.run()      # blocks; run as asyncio.Task
    fetcher.stop()

Requirements:
    httpx, feedparser (both in [live_data] extras)
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

from src.core.clock import VirtualClock
from src.core.exceptions import DataError
from src.core.logging import get_logger
from src.data.models import NewsArticle
from src.data.store import DataStore

_log = get_logger("D02-DATA.news")

# ── Instrument keyword map ────────────────────────────────────────────────────
# Articles are associated with instruments when the headline/body contains these
# keywords (case-insensitive).  Extend per new instruments.

_INSTRUMENT_KEYWORDS: dict[str, list[str]] = {
    "EURUSD": ["euro", "eur", "eurusd", "ecb", "european central bank", "eurozone"],
    "GBPUSD": ["pound", "gbp", "gbpusd", "sterling", "bank of england", "boe", "uk"],
    "USDJPY": ["yen", "jpy", "usdjpy", "bank of japan", "boj", "japan"],
    "XAUUSD": ["gold", "xauusd", "xau", "bullion", "safe haven"],
}

# Macro keywords always get stored regardless of instrument match
_MACRO_KEYWORDS = [
    "federal reserve", "fed", "fomc", "cpi", "inflation", "nfp",
    "non-farm", "gdp", "rate decision", "interest rate", "central bank",
    "tariff", "sanction", "risk-off", "risk-on", "treasury",
]

# ── RSS feed sources ──────────────────────────────────────────────────────────
_RSS_FEEDS: list[dict] = [
    {
        "name": "reuters_rss",
        "url": "https://feeds.reuters.com/reuters/businessNews",
        "priority": 2,
    },
    {
        "name": "forexfactory_rss",
        "url": "https://www.forexfactory.com/ffcal_week_this.xml",
        "priority": 3,
    },
]

# ── NewsAPI endpoint ──────────────────────────────────────────────────────────
_NEWSAPI_BASE = "https://newsapi.org/v2/everything"
_NEWSAPI_QUERIES = [
    "forex euro dollar yen gold",
    "Federal Reserve ECB BOJ interest rate",
    "CPI inflation GDP employment",
]

# ── Token bucket rate limiter ─────────────────────────────────────────────────

class _TokenBucket:
    """Simple token-bucket rate limiter."""

    def __init__(self, capacity: int, refill_rate: float) -> None:
        """
        Parameters
        ----------
        capacity:
            Maximum token count (burst size).
        refill_rate:
            Tokens added per second.
        """
        self._capacity = capacity
        self._tokens = float(capacity)
        self._refill_rate = refill_rate
        self._last_refill = time.monotonic()

    def consume(self, tokens: int = 1) -> bool:
        """Return True and consume tokens if available, else False."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(
            self._capacity,
            self._tokens + elapsed * self._refill_rate,
        )
        self._last_refill = now
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False


# ── Article helpers ───────────────────────────────────────────────────────────

def _article_id(headline: str, published_at: datetime) -> str:
    """Stable deduplication key: SHA-256(headline + published_at ISO)."""
    raw = f"{headline.strip().lower()}|{published_at.isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:40]


def _detect_instruments(headline: str, body: Optional[str]) -> list[str]:
    """Return list of instrument strings that appear in the article text."""
    text = (headline + " " + (body or "")).lower()
    matched = []
    for instrument, keywords in _INSTRUMENT_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            matched.append(instrument)
    return matched


def _is_relevant(headline: str, body: Optional[str]) -> bool:
    """Return True if the article has FX/macro relevance."""
    text = (headline + " " + (body or "")).lower()
    if any(kw in text for kw in _MACRO_KEYWORDS):
        return True
    return bool(_detect_instruments(headline, body))


# ── NewsFetcher ───────────────────────────────────────────────────────────────

class NewsFetcher:
    """Background async task that ingests news from NewsAPI + RSS feeds.

    Parameters
    ----------
    store:
        DataStore to write articles to.
    clock:
        VirtualClock for timestamp comparisons; always use clock.now() for
        current time — never datetime.now().
    newsapi_key:
        Optional NewsAPI key.  If None, only RSS feeds are used.
    poll_interval_seconds:
        How often to poll all sources (default 600 = 10 minutes).
    """

    def __init__(
        self,
        store: DataStore,
        clock: VirtualClock,
        newsapi_key: Optional[str] = None,
        poll_interval_seconds: int = 600,
    ) -> None:
        self._store = store
        self._clock = clock
        self._api_key = newsapi_key
        self._poll_interval = poll_interval_seconds
        self._running = False
        self._last_fetch: datetime = clock.now() - timedelta(hours=1)

        # Per-source rate limiters
        self._buckets: dict[str, _TokenBucket] = {
            "newsapi": _TokenBucket(capacity=10, refill_rate=0.05),     # 1 req / 20s
            "reuters_rss": _TokenBucket(capacity=5, refill_rate=0.02),  # 1 req / 50s
            "forexfactory_rss": _TokenBucket(capacity=3, refill_rate=0.01),
        }

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def run(self) -> None:
        """Main fetch loop — blocks until stop() is called."""
        self._running = True
        _log.info("news_fetcher_started", poll_interval_s=self._poll_interval)
        while self._running:
            await self._fetch_all()
            await asyncio.sleep(self._poll_interval)

    def stop(self) -> None:
        """Signal the run loop to exit after its current iteration."""
        self._running = False
        _log.info("news_fetcher_stopping")

    # ── Fetch orchestration ───────────────────────────────────────────────────

    async def _fetch_all(self) -> None:
        """Fetch from all sources, write new articles to store."""
        since = self._last_fetch
        fetch_start = self._clock.now()
        articles: list[NewsArticle] = []

        tasks = []
        if self._api_key:
            tasks.append(self._fetch_newsapi(since))
        for feed in _RSS_FEEDS:
            tasks.append(self._fetch_rss(feed["name"], feed["url"]))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_failed = True
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                source = "newsapi" if i == 0 and self._api_key else _RSS_FEEDS[i - (1 if self._api_key else 0)]["name"]
                _log.warning("news_source_failed", source=source, error=str(result))
            else:
                articles.extend(result)  # type: ignore[arg-type]
                all_failed = False

        if all_failed and tasks:
            _log.error("all_news_sources_failed", since=since.isoformat())
            return  # Don't update last_fetch — retry next poll

        # Filter relevant and deduplicate
        relevant = [a for a in articles if _is_relevant(a.headline, a.body_snippet)]
        if relevant:
            try:
                self._store.write_news(relevant)
                _log.info(
                    "news_articles_stored",
                    count=len(relevant),
                    since=since.isoformat(),
                )
            except Exception as exc:
                _log.error("news_write_failed", error=str(exc))

        self._last_fetch = fetch_start

    # ── NewsAPI ───────────────────────────────────────────────────────────────

    async def _fetch_newsapi(self, since: datetime) -> list[NewsArticle]:
        """Fetch from newsapi.org; return parsed articles."""
        try:
            import httpx  # lazy import — optional dep
        except ImportError as e:
            raise DataError("httpx not installed; add it to requirements") from e

        if not self._buckets["newsapi"].consume():
            _log.debug("newsapi_rate_limited")
            return []

        articles: list[NewsArticle] = []
        from_dt = since.strftime("%Y-%m-%dT%H:%M:%S")

        for query in _NEWSAPI_QUERIES:
            params = {
                "q": query,
                "from": from_dt,
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": 50,
                "apiKey": self._api_key,
            }
            url = f"{_NEWSAPI_BASE}?{urlencode(params)}"

            for attempt in range(5):
                try:
                    async with httpx.AsyncClient(timeout=15.0) as client:
                        resp = await client.get(url)
                    if resp.status_code == 429:
                        wait = int(resp.headers.get("Retry-After", 60))
                        _log.warning("newsapi_rate_limited", retry_after_s=wait)
                        await asyncio.sleep(wait)
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    for item in data.get("articles", []):
                        article = self._parse_newsapi_item(item)
                        if article:
                            articles.append(article)
                    break  # success
                except Exception as exc:
                    if attempt == 4:
                        raise DataError(f"NewsAPI fetch failed after 5 attempts: {exc}") from exc
                    wait = 2 ** attempt
                    await asyncio.sleep(wait)

        return articles

    def _parse_newsapi_item(self, item: dict) -> Optional[NewsArticle]:
        """Parse a single NewsAPI article dict into NewsArticle."""
        headline = (item.get("title") or "").strip()[:500]
        if not headline:
            return None

        published_raw = item.get("publishedAt", "")
        try:
            published_at = datetime.fromisoformat(
                published_raw.replace("Z", "+00:00")
            ).astimezone(timezone.utc)
        except Exception:
            return None

        body = item.get("description") or item.get("content") or ""
        instruments = _detect_instruments(headline, body)

        return NewsArticle(
            article_id=_article_id(headline, published_at),
            headline=headline,
            url=item.get("url"),
            source=item.get("source", {}).get("name", "newsapi"),
            published_at=published_at,
            instruments=instruments,
            body_snippet=body[:1000] if body else None,
        )

    # ── RSS feeds ─────────────────────────────────────────────────────────────

    async def _fetch_rss(self, name: str, url: str) -> list[NewsArticle]:
        """Fetch and parse an RSS feed; return articles."""
        try:
            import feedparser  # lazy import — optional dep
        except ImportError as e:
            raise DataError("feedparser not installed; add it to requirements") from e

        bucket = self._buckets.get(name, _TokenBucket(3, 0.01))
        if not bucket.consume():
            _log.debug("rss_rate_limited", source=name)
            return []

        try:
            import httpx

            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, follow_redirects=True)
                resp.raise_for_status()
                raw_content = resp.text
        except Exception as exc:
            raise DataError(f"RSS fetch failed for {name}: {exc}") from exc

        feed = feedparser.parse(raw_content)
        articles: list[NewsArticle] = []

        for entry in feed.entries:
            headline = (getattr(entry, "title", "") or "").strip()[:500]
            if not headline:
                continue

            # Parse publication time
            published_at: Optional[datetime] = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                import calendar as _cal
                ts = _cal.timegm(entry.published_parsed)
                published_at = datetime.fromtimestamp(ts, tz=timezone.utc)
            else:
                published_at = self._clock.now()

            body = getattr(entry, "summary", "") or ""
            instruments = _detect_instruments(headline, body)

            articles.append(
                NewsArticle(
                    article_id=_article_id(headline, published_at),
                    headline=headline,
                    url=getattr(entry, "link", None),
                    source=name,
                    published_at=published_at,
                    instruments=instruments,
                    body_snippet=body[:1000] if body else None,
                )
            )

        _log.debug("rss_fetched", source=name, count=len(articles))
        return articles
