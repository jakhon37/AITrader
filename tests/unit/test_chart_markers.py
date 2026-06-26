"""Unit tests for chart marker store (alternating LONG/SHORT dedup)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.core.contracts import (
    Direction,
    Instrument,
    MarketRegime,
    OrderSide,
    SignalSource,
    SignalStrength,
    TechnicalSignal,
    Timeframe,
    TradeSignal,
)
from src.decision.chart_markers import ChartMarkerStore


def _now() -> datetime:
    return datetime(2026, 6, 26, 12, 0, 0, tzinfo=timezone.utc)


def _trade(
    direction: Direction,
    *,
    bar_time: datetime | None = None,
    signal_id: str = "sig-1",
) -> TradeSignal:
    ts = bar_time or _now()
    t_sig = TechnicalSignal(
        signal_id="tech-1",
        instrument=Instrument.EURUSD,
        timestamp=ts,
        valid_until=ts + timedelta(hours=1),
        direction=direction,
        confidence=0.8,
        strength=SignalStrength.STRONG,
        regime=MarketRegime.TRENDING,
        confluence_score=0.9,
        per_timeframe=[],
        primary_tf=Timeframe.H1,
        entry_price=1.0850,
        stop_loss=1.0800,
        take_profit=1.0950,
    )
    return TradeSignal(
        signal_id=signal_id,
        instrument=Instrument.EURUSD,
        timestamp=ts,
        valid_until=ts + timedelta(hours=1),
        direction=direction,
        confidence=0.8,
        strength=SignalStrength.STRONG,
        fundamental_weight=0.3,
        technical_weight=0.7,
        suggested_side=(
            OrderSide.BUY
            if direction == Direction.LONG
            else OrderSide.SELL
            if direction == Direction.SHORT
            else None
        ),
        suggested_entry=1.0850,
        suggested_sl=1.0800,
        suggested_tp=1.0950,
        suggested_size=0.1,
        narrative="test",
        sources=SignalSource(fundamental=None, technical=t_sig),
        model_version=None,
    )


def test_chart_marker_store_skips_neutral(tmp_path) -> None:
    store = ChartMarkerStore(tmp_path / "chart_markers.db")
    marker = store.try_add_from_trade(_trade(Direction.NEUTRAL))
    assert marker is None
    assert store.list_markers() == []


def test_chart_marker_store_first_long_then_skips_repeat(tmp_path) -> None:
    store = ChartMarkerStore(tmp_path / "chart_markers.db")
    t0 = _now()

    m1 = store.try_add_from_trade(_trade(Direction.LONG, bar_time=t0, signal_id="s1"))
    assert m1 is not None
    assert m1.direction == Direction.LONG

    m2 = store.try_add_from_trade(
        _trade(Direction.LONG, bar_time=t0 + timedelta(hours=1), signal_id="s2")
    )
    assert m2 is None
    assert len(store.list_markers()) == 1


def test_chart_marker_store_alternates_long_short(tmp_path) -> None:
    store = ChartMarkerStore(tmp_path / "chart_markers.db")
    t0 = _now()

    assert store.try_add_from_trade(_trade(Direction.LONG, bar_time=t0, signal_id="s1"))
    assert store.try_add_from_trade(
        _trade(Direction.SHORT, bar_time=t0 + timedelta(hours=1), signal_id="s2")
    )
    assert store.try_add_from_trade(
        _trade(Direction.LONG, bar_time=t0 + timedelta(hours=2), signal_id="s3")
    )

    markers = store.list_markers(Instrument.EURUSD)
    assert len(markers) == 3
    assert [m.direction for m in markers] == [
        Direction.LONG,
        Direction.SHORT,
        Direction.LONG,
    ]


def test_chart_marker_store_skips_same_bar(tmp_path) -> None:
    store = ChartMarkerStore(tmp_path / "chart_markers.db")
    t0 = _now()

    store.try_add_from_trade(_trade(Direction.LONG, bar_time=t0, signal_id="s1"))
    # Opposite direction but same bar should still be blocked if last has same bar_time
    # (only one marker per bar via unique index)
    m = store.try_add_from_trade(_trade(Direction.SHORT, bar_time=t0, signal_id="s2"))
    # Different direction on same bar: last check is same bar_time as last marker
    assert m is None