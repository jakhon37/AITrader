"""Unit tests for fundamental signal SQLite persistence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.core.contracts import (
    Direction,
    FundamentalEventType,
    FundamentalSignal,
    Instrument,
    SignalStrength,
)
from src.fundamental.signal_store import FundamentalSignalStore


def _signal(
    signal_id: str,
    *,
    hours_ago: float = 0.0,
    valid_hours: float = 6.0,
    headline: str = "Fed holds rates steady",
) -> FundamentalSignal:
    ts = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return FundamentalSignal(
        signal_id=signal_id,
        instrument=Instrument.EURUSD,
        timestamp=ts,
        valid_until=ts + timedelta(hours=valid_hours),
        direction=Direction.NEUTRAL,
        confidence=0.5,
        strength=SignalStrength.MODERATE,
        sentiment_score=0.1,
        event_type=FundamentalEventType.MARKET_RISK,
        source_headline=headline,
        source_url=None,
        decay_hours=6.0,
        narrative="Test narrative",
        triggering_event=None,
    )


@pytest.fixture()
def store(tmp_path) -> FundamentalSignalStore:
    return FundamentalSignalStore(tmp_path / "fundamental_signals.db")


def test_upsert_and_list_recent_newest_first(store: FundamentalSignalStore) -> None:
    store.upsert(_signal("older", hours_ago=2.0, headline="Older headline"))
    store.upsert(_signal("newer", hours_ago=0.5, headline="Newer headline"))

    rows = store.list_recent(limit=10)
    assert [row.signal_id for row in rows] == ["newer", "older"]


def test_valid_only_filters_expired(store: FundamentalSignalStore) -> None:
    store.upsert(_signal("expired", hours_ago=10.0, valid_hours=1.0))
    store.upsert(_signal("active", hours_ago=0.5, valid_hours=12.0))

    valid = store.list_recent(limit=10, valid_only=True)
    assert [row.signal_id for row in valid] == ["active"]


def test_purge_expired_and_old(store: FundamentalSignalStore) -> None:
    store.upsert(_signal("ancient", hours_ago=400.0, valid_hours=1.0))
    store.upsert(_signal("expired", hours_ago=5.0, valid_hours=1.0))
    store.upsert(_signal("fresh", hours_ago=0.2, valid_hours=12.0))

    store.purge_expired()
    store.purge_older_than(days=30)

    remaining = store.list_recent(limit=10, valid_only=False)
    assert [row.signal_id for row in remaining] == ["fresh"]