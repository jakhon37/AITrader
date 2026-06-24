"""Tests for independent position legs in MockExecutionEngine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.backtest.engine.event_driven import MockExecutionEngine
from src.core.bus import InProcessBus
from src.core.contracts import (
    BusChannel,
    Direction,
    Instrument,
    OrderSide,
    SignalSource,
    SignalStrength,
    TradeSignal,
)
from src.core.ids import new_signal_id


def _trade_signal(
    *,
    side: OrderSide,
    entry: float = 1.10,
    signal_id: str | None = None,
) -> TradeSignal:
    sig_id = signal_id or new_signal_id()
    ts = datetime(2024, 1, 2, tzinfo=timezone.utc)
    return TradeSignal(
        signal_id=sig_id,
        instrument=Instrument.EURUSD,
        timestamp=ts,
        valid_until=ts + timedelta(hours=1),
        direction=Direction.LONG if side == OrderSide.BUY else Direction.SHORT,
        confidence=1.0,
        strength=SignalStrength.STRONG,
        fundamental_weight=0.0,
        technical_weight=0.0,
        suggested_side=side,
        suggested_entry=entry,
        suggested_sl=None,
        suggested_tp=None,
        suggested_size=0.1,
        narrative="test",
        sources=SignalSource(fundamental=None, technical=None),
        model_version="manual",
        is_limit=False,
    )


def test_opposite_side_legs_coexist() -> None:
    """Opening short must not auto-close an existing long leg."""
    import asyncio

    async def _run() -> None:
        bus = InProcessBus()
        engine = MockExecutionEngine(bus, 10_000.0)
        await engine.start()

        long_sig = _trade_signal(side=OrderSide.BUY)
        short_sig = _trade_signal(side=OrderSide.SELL, entry=1.09)

        await bus.publish(BusChannel.TRADE_SIGNAL, long_sig)
        await bus.publish(BusChannel.TRADE_SIGNAL, short_sig)

        assert len(engine.position_legs) == 2
        sides = {leg["side"] for leg in engine.position_legs.values()}
        assert sides == {OrderSide.BUY, OrderSide.SELL}

        await engine.stop()

    asyncio.run(_run())