"""End-to-end integration tests for multi-tier signal spine (Tiers 2–4)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.core.bus import create_bus
from src.core.config import AppConfig
from src.core.contracts import (
    BusChannel,
    Direction,
    EconomicEvent,
    FundamentalEventType,
    FundamentalSignal,
    Instrument,
    MarketRegime,
    OrderSide,
    SignalStrength,
    TechnicalSignal,
    Timeframe,
    TradeSignal,
    SignalSource,
)
from src.decision.engine import DecisionEngine
from src.execution.circuit_breaker import CircuitBreaker
from src.execution.engine import ExecutionEngine


@pytest.mark.asyncio
async def test_fundamental_technical_to_trade_signal_spine() -> None:
    """Tier 3: FUNDAMENTAL + TECHNICAL → fused TRADE_SIGNAL."""
    bus = create_bus("memory")
    decision = DecisionEngine(config=AppConfig(), bus=bus)
    trade_signals: list[TradeSignal] = []

    async def capture(payload: TradeSignal) -> None:
        trade_signals.append(payload)

    await bus.subscribe(BusChannel.TRADE_SIGNAL, capture)
    await decision.start()

    now = datetime.now(timezone.utc)
    f_sig = FundamentalSignal(
        signal_id="f-e2e",
        instrument=Instrument.EURUSD,
        timestamp=now,
        valid_until=now + timedelta(hours=2),
        direction=Direction.LONG,
        confidence=0.8,
        strength=SignalStrength.STRONG,
        sentiment_score=0.6,
        event_type=FundamentalEventType.ECONOMIC_DATA,
        source_headline="Strong Euro data",
        source_url=None,
        decay_hours=2.0,
        narrative="Bullish macro",
        triggering_event=None,
    )
    t_sig = TechnicalSignal(
        signal_id="t-e2e",
        instrument=Instrument.EURUSD,
        timestamp=now,
        valid_until=now + timedelta(hours=1),
        direction=Direction.LONG,
        confidence=0.75,
        strength=SignalStrength.STRONG,
        regime=MarketRegime.TRENDING,
        confluence_score=0.85,
        per_timeframe=[],
        primary_tf=Timeframe.H1,
        entry_price=1.0850,
        stop_loss=1.0800,
        take_profit=1.0950,
    )

    await bus.publish(BusChannel.FUNDAMENTAL_SIGNAL, f_sig)
    await bus.publish(BusChannel.TECHNICAL_SIGNAL, t_sig)

    assert len(trade_signals) >= 1
    sig = trade_signals[-1]
    assert sig.instrument == Instrument.EURUSD
    assert sig.direction == Direction.LONG
    assert sig.sources.fundamental is not None
    assert sig.sources.technical is not None
    assert sig.fundamental_weight > 0
    assert sig.technical_weight > 0

    await decision.stop()


@pytest.mark.asyncio
async def test_high_impact_event_blocks_trading() -> None:
    """Tier 4: pre-release high-impact ECONOMIC_EVENT activates news_halt window."""
    breaker = CircuitBreaker(initial_capital=100_000.0)
    release = datetime(2026, 6, 25, 14, 0, tzinfo=timezone.utc)
    event = EconomicEvent(
        signal_id="evt-halt",
        timestamp=release,
        name="US NFP",
        impact="high",
        affected_pairs=[Instrument.EURUSD],
        actual=None,
        forecast=200.0,
        previous=180.0,
    )

    breaker.handle_economic_event(event, news_halt_minutes=30)

    during = release - timedelta(minutes=15)
    assert breaker.is_trading_allowed(Instrument.EURUSD, current_time=during) is False
    assert breaker.is_trading_allowed(Instrument.EURUSD, current_time=release + timedelta(hours=2)) is True


@pytest.mark.asyncio
async def test_trade_signal_rejected_during_news_halt() -> None:
    """Tier 4: ExecutionEngine rejects orders while circuit breaker news halt active."""
    bus = create_bus("memory")
    cfg = AppConfig()
    engine = ExecutionEngine(config=cfg, bus=bus)
    engine.is_running = True
    await engine._subscribe_channels()

    release = datetime.now(timezone.utc) + timedelta(minutes=10)
    event = EconomicEvent(
        signal_id="evt-live",
        timestamp=release,
        name="FOMC Rate Decision",
        impact="high",
        affected_pairs=[Instrument.EURUSD],
        actual=None,
    )
    await bus.publish(BusChannel.ECONOMIC_EVENT, event)

    now = datetime.now(timezone.utc)
    trade = TradeSignal(
        signal_id="trade-halt",
        instrument=Instrument.EURUSD,
        timestamp=now,
        valid_until=now + timedelta(hours=1),
        direction=Direction.LONG,
        confidence=0.9,
        strength=SignalStrength.STRONG,
        fundamental_weight=0.3,
        technical_weight=0.7,
        suggested_side=OrderSide.BUY,
        suggested_entry=1.0850,
        suggested_sl=1.0800,
        suggested_tp=1.0950,
        suggested_size=0.1,
        narrative="Should be blocked",
        sources=SignalSource(fundamental=None, technical=None),
        model_version=None,
    )
    await bus.publish(BusChannel.TRADE_SIGNAL, trade)

    assert engine.position_manager.get_num_positions() == 0
    assert engine._last_action == "halted"
    await engine._unsubscribe_channels()