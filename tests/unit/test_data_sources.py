"""Unit tests for D02-DATA Phase 1b: news and calendar SQLite layers.

Tests:
  News:
    - write_news / get_news round-trip
    - instrument filtering
    - deduplication (duplicate article_id silently ignored)
    - tz-naive rejection
    - empty list is a no-op (no error)

  Calendar:
    - write_calendar_events / get_economic_events round-trip
    - impact filtering
    - INSERT OR REPLACE (same event_id updates row)
    - mark_event_notified flips the flag
    - tz-naive rejection
    - invalid impact_filter raises DataError

  FredFetcher:
    - _ensure_schema creates DB
    - get_latest returns None when empty
    - get_series returns correct rows
    - _parse_newsapi_item parses correctly
    - _article_id is deterministic
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.core.contracts import Instrument
from src.core.exceptions import DataError
from src.data.models import NewsArticle, RawCalendarEvent
from src.data.store import DataStore


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def store(tmp_path: Path) -> DataStore:
    return DataStore(base_dir=tmp_path)


def _article(
    headline: str = "Euro rises on ECB decision",
    published_offset_hours: int = 0,
    instruments: list[str] | None = None,
    article_id: str | None = None,
) -> NewsArticle:
    pub = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc) + timedelta(
        hours=published_offset_hours
    )
    from src.data.sources.news_fetcher import _article_id
    aid = article_id or _article_id(headline, pub)
    return NewsArticle(
        article_id=aid,
        headline=headline,
        url="https://example.com/article",
        source="newsapi",
        published_at=pub,
        instruments=instruments or ["EURUSD"],
        body_snippet="ECB raised rates by 25 bps.",
    )


def _event(
    name: str = "US CPI YoY",
    hours_offset: int = 0,
    impact: str = "high",
    actual: float | None = None,
    event_id: str | None = None,
) -> RawCalendarEvent:
    ts = datetime(2025, 1, 15, 14, 30, tzinfo=timezone.utc) + timedelta(
        hours=hours_offset
    )
    return RawCalendarEvent(
        event_id=event_id or f"us_cpi_yoy_{ts.strftime('%Y%m%dT%H%M')}",
        name=name,
        timestamp=ts,
        impact=impact,  # type: ignore[arg-type]
        instruments=["EURUSD", "GBPUSD"],
        actual=actual,
        forecast=3.1,
        previous=3.2,
        fetched_at=datetime.now(tz=timezone.utc),
    )


# ── News: write / get ─────────────────────────────────────────────────────────

class TestNews:
    def test_round_trip(self, store: DataStore) -> None:
        a = _article()
        store.write_news([a])

        start = datetime(2025, 1, 15, 0, 0, tzinfo=timezone.utc)
        end = datetime(2025, 1, 15, 23, 59, tzinfo=timezone.utc)
        results = store.get_news(None, start, end)

        assert len(results) == 1
        assert results[0].headline == a.headline
        assert results[0].source == "newsapi"

    def test_instrument_filter_matches(self, store: DataStore) -> None:
        a1 = _article(instruments=["EURUSD"], article_id="a1")
        a2 = _article(
            headline="Gold safe haven surge",
            instruments=["XAUUSD"],
            article_id="a2",
            published_offset_hours=1,
        )
        store.write_news([a1, a2])

        start = datetime(2025, 1, 15, 0, 0, tzinfo=timezone.utc)
        end = datetime(2025, 1, 15, 23, 59, tzinfo=timezone.utc)

        eur_results = store.get_news(Instrument.EURUSD, start, end)
        assert len(eur_results) == 1
        assert "EURUSD" in eur_results[0].instruments

        gold_results = store.get_news(Instrument.XAUUSD, start, end)
        assert len(gold_results) == 1
        assert "XAUUSD" in gold_results[0].instruments

    def test_instrument_filter_no_match(self, store: DataStore) -> None:
        a = _article(instruments=["EURUSD"])
        store.write_news([a])

        start = datetime(2025, 1, 15, 0, 0, tzinfo=timezone.utc)
        end = datetime(2025, 1, 15, 23, 59, tzinfo=timezone.utc)
        results = store.get_news(Instrument.XAUUSD, start, end)
        assert results == []

    def test_deduplication(self, store: DataStore) -> None:
        """Duplicate article_id: second insert is silently ignored."""
        a = _article(article_id="dup-001")
        store.write_news([a])
        store.write_news([a])  # same id — should not raise or duplicate

        start = datetime(2025, 1, 15, 0, 0, tzinfo=timezone.utc)
        end = datetime(2025, 1, 15, 23, 59, tzinfo=timezone.utc)
        results = store.get_news(None, start, end)
        assert len(results) == 1

    def test_empty_list_is_noop(self, store: DataStore) -> None:
        store.write_news([])  # must not raise

    def test_tz_naive_raises(self, store: DataStore) -> None:
        naive_start = datetime(2025, 1, 15, 0, 0)  # no tzinfo
        naive_end = datetime(2025, 1, 15, 23, 59)
        with pytest.raises(DataError, match="UTC-aware"):
            store.get_news(None, naive_start, naive_end)

    def test_out_of_range_returns_empty(self, store: DataStore) -> None:
        a = _article()
        store.write_news([a])

        start = datetime(2025, 6, 1, 0, 0, tzinfo=timezone.utc)
        end = datetime(2025, 6, 30, 0, 0, tzinfo=timezone.utc)
        results = store.get_news(None, start, end)
        assert results == []

    def test_sorted_ascending(self, store: DataStore) -> None:
        articles = [
            _article(published_offset_hours=i, article_id=f"art-{i}")
            for i in range(5)
        ]
        # Write in reverse order
        store.write_news(list(reversed(articles)))

        start = datetime(2025, 1, 15, 0, 0, tzinfo=timezone.utc)
        end = datetime(2025, 1, 16, 0, 0, tzinfo=timezone.utc)
        results = store.get_news(None, start, end)

        timestamps = [r.published_at for r in results]
        assert timestamps == sorted(timestamps)


# ── Calendar: write / get ─────────────────────────────────────────────────────

class TestCalendar:
    def test_round_trip(self, store: DataStore) -> None:
        e = _event()
        store.write_calendar_events([e])

        start = datetime(2025, 1, 15, 0, 0, tzinfo=timezone.utc)
        end = datetime(2025, 1, 15, 23, 59, tzinfo=timezone.utc)
        results = store.get_economic_events(start, end)

        assert len(results) == 1
        assert results[0].name == "US CPI YoY"
        assert results[0].impact == "high"
        assert "EURUSD" in results[0].instruments

    def test_impact_filter_high(self, store: DataStore) -> None:
        events = [
            _event(name="High Impact Event", impact="high", event_id="hi"),
            _event(name="Low Impact Event", impact="low", event_id="lo", hours_offset=1),
        ]
        store.write_calendar_events(events)

        start = datetime(2025, 1, 15, 0, 0, tzinfo=timezone.utc)
        end = datetime(2025, 1, 16, 0, 0, tzinfo=timezone.utc)

        high_only = store.get_economic_events(start, end, impact_filter="high")
        assert len(high_only) == 1
        assert high_only[0].name == "High Impact Event"

    def test_insert_or_replace_updates_actuals(self, store: DataStore) -> None:
        """Same event_id with updated actuals replaces the row."""
        e = _event(event_id="cpi-001")
        store.write_calendar_events([e])

        e_with_actual = _event(event_id="cpi-001", actual=3.5)
        store.write_calendar_events([e_with_actual])

        start = datetime(2025, 1, 15, 0, 0, tzinfo=timezone.utc)
        end = datetime(2025, 1, 15, 23, 59, tzinfo=timezone.utc)
        results = store.get_economic_events(start, end)
        assert len(results) == 1
        assert results[0].actual == pytest.approx(3.5)

    def test_mark_event_notified_pre(self, store: DataStore) -> None:
        e = _event(event_id="notify-001")
        store.write_calendar_events([e])

        store.mark_event_notified("notify-001", pre=True)

        start = datetime(2025, 1, 15, 0, 0, tzinfo=timezone.utc)
        end = datetime(2025, 1, 15, 23, 59, tzinfo=timezone.utc)
        results = store.get_economic_events(start, end)
        assert results[0].pre_release_notified is True
        assert results[0].post_release_notified is False

    def test_mark_event_notified_post(self, store: DataStore) -> None:
        e = _event(event_id="notify-002")
        store.write_calendar_events([e])

        store.mark_event_notified("notify-002", post=True)

        start = datetime(2025, 1, 15, 0, 0, tzinfo=timezone.utc)
        end = datetime(2025, 1, 15, 23, 59, tzinfo=timezone.utc)
        results = store.get_economic_events(start, end)
        assert results[0].post_release_notified is True

    def test_empty_list_is_noop(self, store: DataStore) -> None:
        store.write_calendar_events([])

    def test_tz_naive_raises(self, store: DataStore) -> None:
        naive = datetime(2025, 1, 15)
        with pytest.raises(DataError, match="UTC-aware"):
            store.get_economic_events(naive, naive)

    def test_invalid_impact_filter_raises(self, store: DataStore) -> None:
        start = datetime(2025, 1, 15, 0, 0, tzinfo=timezone.utc)
        end = datetime(2025, 1, 15, 23, 59, tzinfo=timezone.utc)
        with pytest.raises(DataError, match="invalid impact_filter"):
            store.get_economic_events(start, end, impact_filter="critical")

    def test_sorted_ascending(self, store: DataStore) -> None:
        events = [_event(hours_offset=i, event_id=f"ev-{i}") for i in range(4)]
        store.write_calendar_events(list(reversed(events)))

        start = datetime(2025, 1, 15, 0, 0, tzinfo=timezone.utc)
        end = datetime(2025, 1, 16, 0, 0, tzinfo=timezone.utc)
        results = store.get_economic_events(start, end)
        timestamps = [r.timestamp for r in results]
        assert timestamps == sorted(timestamps)

    def test_out_of_range_returns_empty(self, store: DataStore) -> None:
        e = _event()
        store.write_calendar_events([e])

        start = datetime(2025, 6, 1, 0, 0, tzinfo=timezone.utc)
        end = datetime(2025, 6, 30, 0, 0, tzinfo=timezone.utc)
        results = store.get_economic_events(start, end)
        assert results == []


# ── NewsFetcher helpers ───────────────────────────────────────────────────────

class TestNewsFetcherHelpers:
    def test_article_id_is_deterministic(self) -> None:
        from src.data.sources.news_fetcher import _article_id

        pub = datetime(2025, 1, 15, 10, tzinfo=timezone.utc)
        id1 = _article_id("EUR/USD rises on ECB", pub)
        id2 = _article_id("EUR/USD rises on ECB", pub)
        assert id1 == id2
        assert len(id1) == 40  # SHA-256[:40]

    def test_article_id_differs_on_different_headline(self) -> None:
        from src.data.sources.news_fetcher import _article_id

        pub = datetime(2025, 1, 15, 10, tzinfo=timezone.utc)
        id1 = _article_id("EUR/USD rises", pub)
        id2 = _article_id("EUR/USD falls", pub)
        assert id1 != id2

    def test_detect_instruments_eurusd(self) -> None:
        from src.data.sources.news_fetcher import _detect_instruments

        result = _detect_instruments("Euro climbs after ECB rate hike", None)
        assert "EURUSD" in result

    def test_detect_instruments_gold(self) -> None:
        from src.data.sources.news_fetcher import _detect_instruments

        result = _detect_instruments("Gold surges as safe haven demand rises", None)
        assert "XAUUSD" in result

    def test_detect_instruments_no_match(self) -> None:
        from src.data.sources.news_fetcher import _detect_instruments

        result = _detect_instruments("Stocks rally on tech earnings", None)
        assert result == []

    def test_is_relevant_macro_keyword(self) -> None:
        from src.data.sources.news_fetcher import _is_relevant

        assert _is_relevant("Federal Reserve holds rates steady", None) is True

    def test_is_relevant_instrument_match(self) -> None:
        from src.data.sources.news_fetcher import _is_relevant

        assert _is_relevant("Yen weakens after BOJ statement", None) is True

    def test_is_relevant_no_match(self) -> None:
        from src.data.sources.news_fetcher import _is_relevant

        assert _is_relevant("Local sports team wins championship", None) is False

    def test_instruments_from_finnhub_related(self) -> None:
        from src.data.sources.news_fetcher import _instruments_from_finnhub_related

        result = _instruments_from_finnhub_related("OANDA:EUR_USD,OANDA:USD_JPY")
        assert result == ["EURUSD", "USDJPY"]

    def test_parse_finnhub_item(self) -> None:
        from src.data.sources.news_fetcher import NewsFetcher
        from unittest.mock import MagicMock

        fetcher = NewsFetcher(store=MagicMock(), clock=MagicMock())
        article = fetcher._parse_finnhub_item(
            {
                "id": 99,
                "datetime": 1719392400,
                "headline": "Euro rises after ECB holds rates",
                "summary": "EURUSD climbed on policy guidance.",
                "source": "Reuters",
                "url": "https://example.com/eur",
                "related": "OANDA:EUR_USD",
            },
            category="forex",
        )
        assert article is not None
        assert article.article_id == "finnhub:99"
        assert article.instruments == ["EURUSD"]
        assert "finnhub/Reuters/forex" in article.source


# ── CalendarFetcher HTML parser ───────────────────────────────────────────────

class TestCalendarParser:
    def test_parse_ff_date_compact_format(self) -> None:
        from src.data.sources.calendar import _parse_ff_date

        parsed = _parse_ff_date("FriJun 26", 2026)
        assert parsed is not None
        assert parsed.year == 2026
        assert parsed.month == 6
        assert parsed.day == 26

    def test_parse_ff_date_legacy_format(self) -> None:
        from src.data.sources.calendar import _parse_ff_date

        parsed = _parse_ff_date("Fri Jun 26", 2026)
        assert parsed is not None
        assert parsed.day == 26

    def test_parse_ff_html_parses_scheduled_row(self) -> None:
        pytest.importorskip("bs4")
        from unittest.mock import MagicMock
        from src.data.sources.calendar import CalendarFetcher

        html = """
        <table class="calendar__table">
          <tr class="calendar__row">
            <td class="calendar__date">FriJun 26</td>
            <td class="calendar__time">7:30am</td>
            <td class="calendar__currency">USD</td>
            <td class="calendar__impact"><span class="icon icon--ff-impact-yel"></span></td>
            <td class="calendar__event"><span>Goods Trade Balance</span></td>
            <td class="calendar__actual"></td>
            <td class="calendar__forecast">-85.0B</td>
            <td class="calendar__previous">-82.4B</td>
          </tr>
        </table>
        """
        clock = MagicMock()
        clock.now.return_value = datetime(2026, 6, 26, 8, 0, tzinfo=timezone.utc)
        fetcher = CalendarFetcher(MagicMock(), MagicMock(), clock)
        events = fetcher._parse_ff_html(html)

        assert len(events) == 1
        assert events[0].name == "Goods Trade Balance"
        assert events[0].impact == "medium"
        assert "EURUSD" in events[0].instruments


# ── FredFetcher: schema + query API ──────────────────────────────────────────

class TestFredFetcher:
    def test_schema_created(self, tmp_path: Path) -> None:
        """Constructor should create the fred.db file and table."""
        import sqlite3
        from unittest.mock import MagicMock
        from src.data.sources.fred import FredFetcher

        clock = MagicMock()
        clock.now.return_value = datetime(2025, 1, 15, tzinfo=timezone.utc)

        FredFetcher(data_base_dir=tmp_path, clock=clock, api_key=None)
        db = tmp_path / "fred.db"
        assert db.exists()

        with sqlite3.connect(db) as conn:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "fred_observations" in tables

    def test_get_latest_returns_none_when_empty(self, tmp_path: Path) -> None:
        from unittest.mock import MagicMock
        from src.data.sources.fred import FredFetcher

        clock = MagicMock()
        clock.now.return_value = datetime(2025, 1, 15, tzinfo=timezone.utc)

        fetcher = FredFetcher(data_base_dir=tmp_path, clock=clock)
        assert fetcher.get_latest("DFF") is None

    def test_get_latest_returns_last_row(self, tmp_path: Path) -> None:
        import sqlite3
        from unittest.mock import MagicMock
        from src.data.sources.fred import FredFetcher

        clock = MagicMock()
        clock.now.return_value = datetime(2025, 1, 15, tzinfo=timezone.utc)
        fetcher = FredFetcher(data_base_dir=tmp_path, clock=clock)

        # Insert two observations
        with sqlite3.connect(tmp_path / "fred.db") as conn:
            conn.executemany(
                "INSERT INTO fred_observations (series_id, date, value, fetched_at) VALUES (?,?,?,?)",
                [
                    ("DFF", "2025-01-13", 5.33, "2025-01-15T00:00:00+00:00"),
                    ("DFF", "2025-01-14", 5.34, "2025-01-15T00:00:00+00:00"),
                ],
            )

        result = fetcher.get_latest("DFF")
        assert result is not None
        date, value = result
        assert date == datetime(2025, 1, 14, tzinfo=timezone.utc)
        assert value == pytest.approx(5.34)

    def test_get_series_range(self, tmp_path: Path) -> None:
        import sqlite3
        from unittest.mock import MagicMock
        from src.data.sources.fred import FredFetcher

        clock = MagicMock()
        clock.now.return_value = datetime(2025, 1, 15, tzinfo=timezone.utc)
        fetcher = FredFetcher(data_base_dir=tmp_path, clock=clock)

        with sqlite3.connect(tmp_path / "fred.db") as conn:
            conn.executemany(
                "INSERT INTO fred_observations (series_id, date, value, fetched_at) VALUES (?,?,?,?)",
                [
                    ("CPIAUCSL", "2025-01-01", 310.1, "2025-01-15T00:00:00+00:00"),
                    ("CPIAUCSL", "2025-02-01", 311.0, "2025-01-15T00:00:00+00:00"),
                    ("CPIAUCSL", "2025-03-01", 312.5, "2025-01-15T00:00:00+00:00"),
                ],
            )

        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 2, 28, tzinfo=timezone.utc)
        rows = fetcher.get_series("CPIAUCSL", start, end)

        assert len(rows) == 2
        assert rows[0][1] == pytest.approx(310.1)
        assert rows[1][1] == pytest.approx(311.0)

    def test_unknown_series_raises(self, tmp_path: Path) -> None:
        from unittest.mock import MagicMock
        from src.data.sources.fred import FredFetcher

        clock = MagicMock()
        clock.now.return_value = datetime(2025, 1, 15, tzinfo=timezone.utc)
        fetcher = FredFetcher(data_base_dir=tmp_path, clock=clock)

        with pytest.raises(DataError, match="Unknown FRED series"):
            fetcher.get_latest("INVALID_SERIES")

    def test_available_series(self, tmp_path: Path) -> None:
        from unittest.mock import MagicMock
        from src.data.sources.fred import FredFetcher

        clock = MagicMock()
        clock.now.return_value = datetime(2025, 1, 15, tzinfo=timezone.utc)
        fetcher = FredFetcher(data_base_dir=tmp_path, clock=clock)

        series = fetcher.available_series()
        assert "DFF" in series
        assert "CPIAUCSL" in series
        assert "UNRATE" in series
        assert "T10Y2Y" in series
