"""Unit tests for Tier 2 live signal spine wiring."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.bus import create_bus
from src.core.config import AppConfig
from src.core.contracts import (
    BusChannel,
    Direction,
    Instrument,
    MarketRegime,
    OHLCVBar,
    SignalStrength,
    TechnicalSignal,
    Timeframe,
    TradeSignal,
)
from src.decision.engine import DecisionEngine
from src.technical.engine import TechnicalEngine


@pytest.mark.asyncio
async def test_ohlcv_to_trade_signal_spine() -> None:
    """OHLCV_BAR → TechnicalEngine → DecisionEngine → TRADE_SIGNAL on shared bus."""
    bus = create_bus("memory")
    store = MagicMock()
    store.get_ohlcv.return_value = MagicMock(empty=False)

    technical = TechnicalEngine(bus=bus, store=store)
    decision = DecisionEngine(config=AppConfig(), bus=bus)

    trade_signals: list[TradeSignal] = []

    async def capture_trade(payload: TradeSignal) -> None:
        trade_signals.append(payload)

    await bus.subscribe(BusChannel.TRADE_SIGNAL, capture_trade)
    await decision.start()

    # Bypass heavy indicator pipeline — inject technical signal as if D04 ran.
    now = datetime.now(timezone.utc)
    t_sig = TechnicalSignal(
        signal_id="t-spine-1",
        instrument=Instrument.EURUSD,
        timestamp=now,
        valid_until=now + timedelta(hours=1),
        direction=Direction.LONG,
        confidence=0.75,
        strength=SignalStrength.STRONG,
        regime=MarketRegime.TRENDING,
        confluence_score=0.8,
        per_timeframe=[],
        primary_tf=Timeframe.H1,
        entry_price=1.0850,
        stop_loss=1.0800,
        take_profit=1.0950,
    )
    await bus.publish(BusChannel.TECHNICAL_SIGNAL, t_sig)

    assert len(trade_signals) == 1
    assert trade_signals[0].instrument == Instrument.EURUSD
    assert trade_signals[0].direction == Direction.LONG

    await decision.stop()


@pytest.mark.asyncio
async def test_technical_engine_ignores_non_primary_timeframe() -> None:
    """D04 only runs fusion on each instrument's primary_tf close."""
    bus = create_bus("memory")
    store = MagicMock()

    technical = TechnicalEngine(bus=bus, store=store)
    published: list[TechnicalSignal] = []

    async def capture_tech(payload: TechnicalSignal) -> None:
        published.append(payload)

    await bus.subscribe(BusChannel.TECHNICAL_SIGNAL, capture_tech)
    await technical.start()

    now = datetime(2024, 6, 10, 14, 0, tzinfo=timezone.utc)
    m1_bar = OHLCVBar(
        signal_id="bar-m1",
        instrument=Instrument.EURUSD,
        timeframe=Timeframe.M1,
        timestamp=now,
        open=1.1,
        high=1.1005,
        low=1.0995,
        close=1.1002,
        volume=100.0,
        source="test",
    )
    await bus.publish(BusChannel.OHLCV_BAR, m1_bar)

    assert len(published) == 0

    await technical.stop()


@pytest.mark.asyncio
async def test_signal_pipeline_pause_resume() -> None:
    from src.api.signal_pipeline import pause_live_signal_pipeline, resume_live_signal_pipeline

    bus = create_bus("memory")
    store = MagicMock()
    technical = TechnicalEngine(bus=bus, store=store)
    decision = DecisionEngine(config=AppConfig(), bus=bus)
    await technical.start()
    await decision.start()

    app = MagicMock()
    app.state.technical_engine = technical
    app.state.decision_engine = decision
    app.state.live_signal_pipeline_paused = False

    await pause_live_signal_pipeline(app)
    assert technical.is_running is False
    assert decision.is_running is False
    assert app.state.live_signal_pipeline_paused is True

    await resume_live_signal_pipeline(app)
    assert technical.is_running is True
    assert decision.is_running is True
    assert app.state.live_signal_pipeline_paused is False

    await technical.stop()
    await decision.stop()