"""D02-DATA — News storage and retrieval mixin using SQLite."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.core.contracts import Instrument
from src.core.exceptions import DataError
from src.core.logging import get_logger
from src.data.models import NewsArticle

_log = get_logger("D02-DATA")


class NewsMixin:
    """Mixin for SQLite-based news article storage.

    Expects self._news_db_path (Path) to be populated by the base class.
    """

    def _init_news_schema(self) -> None:
        """Create news SQLite table if it does not yet exist."""
        with sqlite3.connect(self._news_db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS articles (
                    article_id   TEXT PRIMARY KEY,
                    headline     TEXT NOT NULL,
                    url          TEXT,
                    source       TEXT NOT NULL DEFAULT 'unknown',
                    published_at TEXT NOT NULL,   -- UTC ISO-8601
                    instruments  TEXT NOT NULL DEFAULT '[]', -- JSON list of strings
                    body_snippet TEXT,
                    fetched_at   TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_articles_published "
                "ON articles (published_at)"
            )

    def write_news(self, articles: list[NewsArticle]) -> None:
        """Upsert news articles into SQLite.

        Duplicate article_id rows are silently ignored (INSERT OR IGNORE).
        """
        if not articles:
            return
        rows = [
            (
                a.article_id,
                a.headline,
                a.url,
                a.source,
                a.published_at.isoformat(),
                json.dumps(a.instruments),
                a.body_snippet,
                a.fetched_at.isoformat(),
            )
            for a in articles
        ]
        with sqlite3.connect(self._news_db_path) as conn:
            conn.executemany(
                """
                INSERT OR IGNORE INTO articles
                    (article_id, headline, url, source, published_at,
                     instruments, body_snippet, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        _log.debug("news_written", count=len(rows))

    def get_news(
        self,
        instrument: Optional[Instrument],
        start: datetime,
        end: datetime,
    ) -> list[NewsArticle]:
        """Query news articles in [start, end].

        Parameters
        ----------
        instrument:
            If provided, filter to articles that mention this instrument.
            If None, return all articles in the time range.
        start, end:
            UTC-aware datetimes.

        Returns
        -------
        list[NewsArticle] sorted ascending by published_at.

        Raises
        ------
        DataError
            If start/end are tz-naive.
        """
        if start.tzinfo is None or end.tzinfo is None:
            raise DataError("get_news: start and end must be UTC-aware datetimes.")

        start_iso = start.astimezone(timezone.utc).isoformat()
        end_iso = end.astimezone(timezone.utc).isoformat()

        with sqlite3.connect(self._news_db_path) as conn:
            rows = conn.execute(
                """
                SELECT article_id, headline, url, source, published_at,
                       instruments, body_snippet, fetched_at
                FROM articles
                WHERE published_at >= ? AND published_at <= ?
                ORDER BY published_at ASC
                """,
                (start_iso, end_iso),
            ).fetchall()

        articles: list[NewsArticle] = []
        for row in rows:
            art = NewsArticle(
                article_id=row[0],
                headline=row[1],
                url=row[2],
                source=row[3],
                published_at=datetime.fromisoformat(row[4]),
                instruments=json.loads(row[5] or "[]"),
                body_snippet=row[6],
                fetched_at=datetime.fromisoformat(row[7]),
            )
            if instrument is None or instrument.value in art.instruments:
                articles.append(art)

        _log.debug(
            "news_queried",
            instrument=instrument.value if instrument else "all",
            start=start.date().isoformat(),
            end=end.date().isoformat(),
            count=len(articles),
        )
        return articles

    def purge_news_older_than(self, cutoff: datetime) -> int:
        """Delete articles published before cutoff (UTC-aware)."""
        if cutoff.tzinfo is None:
            raise DataError("purge_news_older_than: cutoff must be UTC-aware.")
        cutoff_iso = cutoff.astimezone(timezone.utc).isoformat()
        with sqlite3.connect(self._news_db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM articles WHERE published_at < ?",
                (cutoff_iso,),
            )
            deleted = cursor.rowcount
        if deleted:
            _log.info("news_purged_old", count=deleted, cutoff=cutoff.date().isoformat())
        return deleted
