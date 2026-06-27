"""Tests for monotonic technical signal persistence (DB source of truth)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from src.api.ws.handlers import setup_ws_bridge
from src.core.contracts import (
    Direction,
    Instrument,
    MarketRegime,
    SignalStrength,
    TechnicalSignal,
    Timeframe,
    TimeframeBias,
)
from src.core.ids import new_signal_id
from src.signals.stores import TechnicalSignalStore
from tests.unit.test_fundamental import MockBus


def _tech_signal(ts: datetime, instrument: Instrument = Instrument.EURUSD) -> TechnicalSignal:
    return TechnicalSignal(
        signal_id=new_signal_id(),
        timestamp=ts,
        valid_until=ts + timedelta(hours=6),
        instrument=instrument,
        direction=Direction.SHORT,
        confidence=0.7,
        strength=SignalStrength.STRONG,
        regime=MarketRegime.RANGING,
        confluence_score=1.0,
        per_timeframe=[
            TimeframeBias(
                timeframe=Timeframe.H1,
                direction=Direction.SHORT,
                confidence=0.7,
                regime=MarketRegime.RANGING,
                indicators={},
                support=None,
                resistance=None,
            )
        ],
        primary_tf=Timeframe.H1,
        entry_price=None,
        stop_loss=None,
        take_profit=None,
    )


@pytest.mark.asyncio
async def test_technical_store_rejects_older_signal(tmp_path) -> None:
    from src.core.contracts import BusChannel

    store = TechnicalSignalStore(tmp_path / "technical.db")
    bus = MockBus()
    await setup_ws_bridge(bus, technical_signal_store=store)

    newer = _tech_signal(datetime(2026, 6, 26, 15, 0, tzinfo=timezone.utc))
    older = _tech_signal(datetime(2026, 6, 26, 0, 0, tzinfo=timezone.utc))

    handler = bus.subscriptions[BusChannel.TECHNICAL_SIGNAL][0]
    await handler(newer)
    await handler(older)

    latest = store.get_latest(Instrument.EURUSD)
    assert latest is not None
    assert latest.timestamp == newer.timestamp