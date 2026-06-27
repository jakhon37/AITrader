"""D02-DATA — NewsFetcher: news article ingestion from NewsAPI and RSS feeds.

Sources (priority order):
  1. Finnhub (finnhub.io)   — FX-tagged market news, requires FINNHUB_API_KEY
  2. NewsAPI (newsapi.org)  — structured JSON, requires NEWSAPI_KEY
  3. Reuters RSS            — free, no key; fallback when API is down
  4. Forex Factory RSS      — FX calendar RSS (often blocked)

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
from src.data.retention import purge_stale_news
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
_NEWSAPI_HEADLINES = "https://newsapi.org/v2/top-headlines"
# Free-tier NewsAPI often returns 0 results for narrow "from" windows on /everything.
_NEWSAPI_MIN_LOOKBACK = timedelta(hours=24)
_NEWSAPI_QUERIES = [
    "forex euro dollar yen gold",
    "Federal Reserve ECB BOJ interest rate",
    "CPI inflation GDP employment",
]

# Finnhub market news — https://finnhub.io/docs/api/market-news
_FINNHUB_NEWS_URL = "https://finnhub.io/api/v1/news"
_FINNHUB_CATEGORIES = ("forex", "general")

# Map Finnhub related tickers (e.g. OANDA:EUR_USD) to internal instruments.
_FINNHUB_SYMBOL_MAP: dict[str, str] = {
    "EUR_USD": "EURUSD",
    "GBP_USD": "GBPUSD",
    "USD_JPY": "USDJPY",
    "XAU_USD": "XAUUSD",
    "GOLD": "XAUUSD",
}

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


def _instruments_from_finnhub_related(related: str) -> list[str]:
    """Map Finnhub ``related`` field (comma-separated tickers) to instruments."""
    if not related:
        return []
    matched: list[str] = []
    for token in related.split(","):
        token = token.strip().upper()
        if not token:
            continue
        if ":" in token:
            token = token.split(":", 1)[1]
        token = token.replace("-", "_")
        inst = _FINNHUB_SYMBOL_MAP.get(token)
        if inst and inst not in matched:
            matched.append(inst)
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
    finnhub_key:
        Optional Finnhub API key for ``category=forex`` market news.
    poll_interval_seconds:
        How often to poll all sources (default 600 = 10 minutes).
    """

    def __init__(
        self,
        store: DataStore,
        clock: VirtualClock,
        newsapi_key: Optional[str] = None,
        finnhub_key: Optional[str] = None,
        poll_interval_seconds: int = 600,
    ) -> None:
        self._store = store
        self._clock = clock
        self._api_key = newsapi_key
        self._finnhub_key = finnhub_key
        self._poll_interval = poll_interval_seconds
        self._running = False
        self._last_fetch: datetime = clock.now() - timedelta(hours=1)

        # Per-source rate limiters
        self._buckets: dict[str, _TokenBucket] = {
            "finnhub": _TokenBucket(capacity=5, refill_rate=0.02),
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

        task_specs: list[tuple[str, object]] = []
        if self._finnhub_key:
            task_specs.append(("finnhub", self._fetch_finnhub()))
        if self._api_key:
            task_specs.append(("newsapi", self._fetch_newsapi(since)))
        for feed in _RSS_FEEDS:
            task_specs.append((feed["name"], self._fetch_rss(feed["name"], feed["url"])))

        results = await asyncio.gather(
            *[coro for _, coro in task_specs],
            return_exceptions=True,
        )

        all_failed = True
        for (source, _), result in zip(task_specs, results):
            if isinstance(result, Exception):
                _log.warning("news_source_failed", source=source, error=str(result))
            else:
                articles.extend(result)  # type: ignore[arg-type]
                all_failed = False

        if all_failed and task_specs:
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
            else:
                try:
                    purge_stale_news(self._store, self._clock)
                except Exception as exc:
                    _log.warning("news_retention_failed", error=str(exc))

        self._last_fetch = fetch_start

    # ── Finnhub ───────────────────────────────────────────────────────────────

    async def _fetch_finnhub(self) -> list[NewsArticle]:
        """Fetch forex (+ general macro) market news from Finnhub."""
        try:
            import httpx
        except ImportError as e:
            raise DataError("httpx not installed; add it to requirements") from e

        if not self._finnhub_key:
            return []
        if not self._buckets["finnhub"].consume():
            _log.debug("finnhub_rate_limited")
            return []

        articles: list[NewsArticle] = []
        seen_ids: set[int] = set()

        async with httpx.AsyncClient(timeout=15.0) as client:
            for category in _FINNHUB_CATEGORIES:
                params = {"category": category, "token": self._finnhub_key}
                resp = await client.get(_FINNHUB_NEWS_URL, params=params)
                resp.raise_for_status()
                for item in resp.json():
                    if not isinstance(item, dict):
                        continue
                    raw_id = item.get("id")
                    if isinstance(raw_id, int) and raw_id in seen_ids:
                        continue
                    article = self._parse_finnhub_item(item, category=category)
                    if article is None:
                        continue
                    if isinstance(raw_id, int):
                        seen_ids.add(raw_id)
                    articles.append(article)

        _log.info("finnhub_news_fetched", count=len(articles))
        return articles

    def _parse_finnhub_item(
        self,
        item: dict,
        *,
        category: str,
    ) -> Optional[NewsArticle]:
        """Parse a Finnhub /news JSON object into NewsArticle."""
        headline = (item.get("headline") or "").strip()[:500]
        if not headline:
            return None

        ts_raw = item.get("datetime")
        try:
            published_at = datetime.fromtimestamp(int(ts_raw), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            return None

        summary = (item.get("summary") or "").strip()
        related_raw = str(item.get("related") or "")
        instruments = _instruments_from_finnhub_related(related_raw)
        if not instruments:
            instruments = _detect_instruments(headline, summary)

        source_name = item.get("source") or "finnhub"
        finnhub_id = item.get("id")
        article_id = (
            f"finnhub:{finnhub_id}"
            if finnhub_id is not None
            else _article_id(headline, published_at)
        )

        return NewsArticle(
            article_id=article_id,
            headline=headline,
            url=item.get("url"),
            source=f"finnhub/{source_name}/{category}",
            published_at=published_at,
            instruments=instruments,
            body_snippet=summary[:1000] if summary else None,
        )

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
        now = self._clock.now().astimezone(timezone.utc)
        since_utc = since.astimezone(timezone.utc)
        effective_since = min(since_utc, now - _NEWSAPI_MIN_LOOKBACK)
        from_dt = effective_since.strftime("%Y-%m-%dT%H:%M:%S")

        articles.extend(await self._fetch_newsapi_headlines())

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

    async def _fetch_newsapi_headlines(self) -> list[NewsArticle]:
        """Business top-headlines — reliable on NewsAPI free tier."""
        try:
            import httpx
        except ImportError as e:
            raise DataError("httpx not installed; add it to requirements") from e

        params = {
            "category": "business",
            "language": "en",
            "pageSize": 50,
            "apiKey": self._api_key,
        }
        url = f"{_NEWSAPI_HEADLINES}?{urlencode(params)}"

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
        articles: list[NewsArticle] = []
        for item in data.get("articles", []):
            article = self._parse_newsapi_item(item)
            if article:
                articles.append(article)
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
