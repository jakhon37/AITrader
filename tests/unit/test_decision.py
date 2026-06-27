"""Unit tests for D05-DECISION."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, List
import pytest

from src.core.clock import LiveClock
from src.core.config import AppConfig, InstrumentConfig, SignalDecayConfig
from src.core.contracts import (
    BusChannel,
    Direction,
    FundamentalEventType,
    FundamentalSignal,
    Instrument,
    MarketRegime,
    OrderSide,
    PortfolioState,
    SignalStrength,
    SystemHealthEvent,
    TechnicalSignal,
    Timeframe,
    TimeframeBias,
    TradeSignal,
)
from src.core.ids import new_signal_id
from src.decision.engine import DecisionEngine
from src.decision.expiry import effective_confidence, is_valid
from src.decision.fusion import combine
from src.decision.narrator import build_narrative
from src.decision.sizer import compute_suggested_size
from src.decision.state import SignalState
from tests.unit.test_fundamental import MockBus


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_signal_expiry() -> None:
    now_utc = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)

    # Valid signal
    sig = FundamentalSignal(
        signal_id=new_signal_id(), instrument=Instrument.EURUSD, timestamp=now_utc - timedelta(hours=1),
        valid_until=now_utc + timedelta(hours=1), direction=Direction.LONG, confidence=0.8,
        strength=SignalStrength.STRONG, sentiment_score=0.6, event_type=FundamentalEventType.ECONOMIC_DATA,
        source_headline="Headline", source_url=None, decay_hours=2.0, narrative=None, triggering_event=None
    )
    assert is_valid(sig, now_utc) is True

    # Decayed confidence check (halfway: 1 hour elapsed of 2 total decay hours)
    eff_conf = effective_confidence(sig, now_utc)
    assert pytest.approx(eff_conf) == 0.4

    # Expired signal
    sig.valid_until = now_utc - timedelta(minutes=1)
    assert is_valid(sig, now_utc) is False
    assert effective_confidence(sig, now_utc) == 0.0


def test_weighted_fusion() -> None:
    now_utc = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)
    decay_cfg = SignalDecayConfig()
    inst_cfg = InstrumentConfig(
        pip_size=0.0001,
        lot_size=100000.0,
        session_hours={"open": "22:00", "close": "22:00"},
        active_timeframes=[],
        primary_timeframe=Timeframe.H1,
        fundamental_weight=0.3,
        technical_weight=0.7,
        signal_decay=decay_cfg,
    )

    t_sig = TechnicalSignal(
        signal_id="t1", instrument=Instrument.EURUSD, timestamp=now_utc, valid_until=now_utc + timedelta(hours=1),
        direction=Direction.LONG, confidence=0.8, strength=SignalStrength.STRONG, regime=MarketRegime.TRENDING,
        confluence_score=1.0, per_timeframe=[], primary_tf=Timeframe.H1, entry_price=1.0850, stop_loss=1.0800, take_profit=1.0950
    )

    # Case 1: No fundamental -> Full weight to technical (1.0 * 0.8 = 0.8)
    fusion_output = combine(None, t_sig, inst_cfg, now_utc)
    assert fusion_output.direction == Direction.LONG
    assert fusion_output.confidence == 0.8
    assert fusion_output.fundamental_weight == 0.0
    assert fusion_output.technical_weight == 1.0

    # Case 2: Concordant F+T (Both LONG: 0.3 * 0.8 + 0.7 * 0.8 = 0.8)
    f_sig = FundamentalSignal(
        signal_id="f1", instrument=Instrument.EURUSD, timestamp=now_utc - timedelta(hours=1),
        valid_until=now_utc + timedelta(hours=3), direction=Direction.LONG, confidence=0.8,
        strength=SignalStrength.STRONG, sentiment_score=0.6, event_type=FundamentalEventType.ECONOMIC_DATA,
        source_headline="Headline", source_url=None, decay_hours=4.0, narrative=None, triggering_event=None
    )
    # At now_utc, 1 hour elapsed of 4 -> remaining = 3/4. Decayed f_confidence = 0.8 * 0.75 = 0.6
    # Score: 0.3 * 0.6 (F) + 0.7 * 0.8 (T) = 0.18 + 0.56 = 0.74
    fusion_output = combine(f_sig, t_sig, inst_cfg, now_utc)
    assert fusion_output.direction == Direction.LONG
    assert pytest.approx(fusion_output.confidence) == 0.74
    assert fusion_output.fundamental_weight == 0.3
    assert fusion_output.technical_weight == 0.7

    # Case 3: Discordant F+T (F is SHORT, T is LONG)
    f_sig.direction = Direction.SHORT
    # Score: 0.3 * -0.6 (F) + 0.7 * 0.8 (T) = -0.18 + 0.56 = 0.38
    fusion_output = combine(f_sig, t_sig, inst_cfg, now_utc)
    assert fusion_output.direction == Direction.LONG
    assert pytest.approx(fusion_output.confidence) == 0.38


def test_position_sizer() -> None:
    inst_cfg = InstrumentConfig(
        pip_size=0.0001,
        lot_size=100000.0,
        session_hours={"open": "22:00", "close": "22:00"},
        active_timeframes=[],
        primary_timeframe=Timeframe.H1,
        max_position_lots=2.0,
    )
    portfolio = PortfolioState(
        signal_id="sig1", timestamp=datetime.now(timezone.utc), execution_mode="paper",
        balance=10000.0, equity=10000.0, margin_used=0.0, free_margin=10000.0,
        open_positions=[], realized_pnl_today=0.0, drawdown_pct=0.0
    )

    # 1. Normal size calculation
    # Stop loss distance = 50 pips (1.0850 - 1.0800)
    # Risk per trade = 10000 * 0.01 = $100
    # Pip value = 0.0001 * 100000 = $10
    # Stop value in cash = 50 * 10 = $500 per lot
    # Size = 100 / 500 = 0.20 lots
    size = compute_suggested_size(
        entry_price=1.0850, sl_price=1.0800, inst_config=inst_cfg,
        portfolio_state=portfolio, risk_pct=0.01
    )
    assert size == 0.20

    # 2. Max position cap check
    # Large account balance -> suggested size exceeds max
    portfolio.equity = 200000.0  # Risk = $2000, size = 4 lots -> capped at 2.0
    size = compute_suggested_size(
        entry_price=1.0850, sl_price=1.0800, inst_config=inst_cfg,
        portfolio_state=portfolio, risk_pct=0.01
    )
    assert size == 2.0

    # 3. Fail safe fallback
    assert compute_suggested_size(None, None, inst_cfg, None) == 0.1


def test_narrator() -> None:
    t_sig = TechnicalSignal(
        signal_id="t1", instrument=Instrument.EURUSD, timestamp=datetime.now(timezone.utc), valid_until=datetime.now(timezone.utc),
        direction=Direction.LONG, confidence=0.8, strength=SignalStrength.STRONG, regime=MarketRegime.TRENDING,
        confluence_score=1.0, per_timeframe=[
            TimeframeBias(
                timeframe=Timeframe.H1, direction=Direction.LONG, confidence=0.8, regime=MarketRegime.TRENDING,
                indicators={"rsi": 32.5, "macd_hist": 0.0004}, support=None, resistance=None
            )
        ], primary_tf=Timeframe.H1, entry_price=1.0850, stop_loss=1.0800, take_profit=1.0950
    )

    narrative = build_narrative(None, t_sig, Direction.LONG)
    assert "Decision: LONG EURUSD" in narrative
    assert "RSI=32.5" in narrative
    assert len(narrative) < 280


@pytest.mark.asyncio
async def test_decision_engine_pipeline() -> None:
    from src.core.config import AppConfig
    cfg = AppConfig()

    bus = MockBus()
    engine = DecisionEngine(config=cfg, bus=bus)
    await engine.start()

    now_utc = datetime.now(timezone.utc)

    # 1. Send fundamental signal (LONG EURUSD)
    f_sig = FundamentalSignal(
        signal_id="f1", instrument=Instrument.EURUSD, timestamp=now_utc, valid_until=now_utc + timedelta(hours=2),
        direction=Direction.LONG, confidence=0.8, strength=SignalStrength.STRONG, sentiment_score=0.6,
        event_type=FundamentalEventType.ECONOMIC_DATA, source_headline="Strong Euro data", source_url=None,
        decay_hours=2.0, narrative=None, triggering_event=None
    )
    await bus.publish(BusChannel.FUNDAMENTAL_SIGNAL, f_sig)

    # 2. Send technical signal to trigger fusion (LONG EURUSD)
    t_sig = TechnicalSignal(
        signal_id="t1", instrument=Instrument.EURUSD, timestamp=now_utc, valid_until=now_utc + timedelta(hours=1),
        direction=Direction.LONG, confidence=0.8, strength=SignalStrength.STRONG, regime=MarketRegime.TRENDING,
        confluence_score=1.0, per_timeframe=[], primary_tf=Timeframe.H1, entry_price=1.0850, stop_loss=1.0800, take_profit=1.0950
    )
    await bus.publish(BusChannel.TECHNICAL_SIGNAL, t_sig)

    # Assert TradeSignal published
    signals = [p[1] for p in bus.published if p[0] == BusChannel.TRADE_SIGNAL]
    assert len(signals) == 1
    sig = signals[0]
    assert sig.instrument == Instrument.EURUSD
    assert sig.direction == Direction.LONG
    assert sig.suggested_side == OrderSide.BUY

    # 3. Test cancellation: Transition to NEUTRAL technical
    bus.published.clear()
    engine.state.fundamental.clear()
    t_sig.direction = Direction.NEUTRAL
    t_sig.confidence = 0.0
    await bus.publish(BusChannel.TECHNICAL_SIGNAL, t_sig)

    # Verify NEUTRAL cancellation signal published
    signals = [p[1] for p in bus.published if p[0] == BusChannel.TRADE_SIGNAL]
    assert len(signals) == 1
    sig = signals[0]
    assert sig.direction == Direction.NEUTRAL
    assert sig.suggested_side is None

    # Sending a second NEUTRAL signal should be silenced (no duplicate spam)
    bus.published.clear()
    await bus.publish(BusChannel.TECHNICAL_SIGNAL, t_sig)
    signals = [p[1] for p in bus.published if p[0] == BusChannel.TRADE_SIGNAL]
    assert len(signals) == 0

    await engine.stop()


@pytest.mark.asyncio
async def test_decision_engine_dedupes_repeated_directional_fusion() -> None:
    cfg = AppConfig()
    bus = MockBus()
    engine = DecisionEngine(config=cfg, bus=bus)
    await engine.start()

    now_utc = datetime.now(timezone.utc)
    t_sig = TechnicalSignal(
        signal_id="t1",
        instrument=Instrument.EURUSD,
        timestamp=now_utc,
        valid_until=now_utc + timedelta(hours=1),
        direction=Direction.LONG,
        confidence=0.8,
        strength=SignalStrength.STRONG,
        regime=MarketRegime.TRENDING,
        confluence_score=1.0,
        per_timeframe=[],
        primary_tf=Timeframe.H1,
        entry_price=1.0850,
        stop_loss=1.0800,
        take_profit=1.0950,
    )
    await bus.publish(BusChannel.TECHNICAL_SIGNAL, t_sig)
    assert len([p for p in bus.published if p[0] == BusChannel.TRADE_SIGNAL]) == 1

    bus.published.clear()
    repeat = t_sig.model_copy(update={"signal_id": "t2"})
    await bus.publish(BusChannel.TECHNICAL_SIGNAL, repeat)
    assert len([p for p in bus.published if p[0] == BusChannel.TRADE_SIGNAL]) == 0

    await engine.stop()
