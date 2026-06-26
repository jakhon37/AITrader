"""Execution skip → Telegram rejected OrderEvent tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.config import AppConfig
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
from src.execution.engine import ExecutionEngine


def _trade_signal() -> TradeSignal:
    from datetime import datetime, timedelta, timezone

    ts = datetime(2026, 6, 26, 12, 0, tzinfo=timezone.utc)
    return TradeSignal(
        signal_id=new_signal_id(),
        instrument=Instrument.EURUSD,
        timestamp=ts,
        valid_until=ts + timedelta(hours=1),
        direction=Direction.LONG,
        confidence=0.6,
        strength=SignalStrength.MODERATE,
        fundamental_weight=0.5,
        technical_weight=0.5,
        suggested_side=OrderSide.BUY,
        suggested_entry=1.10,
        suggested_sl=1.09,
        suggested_tp=1.12,
        suggested_size=0.1,
        narrative="test",
        sources=SignalSource(fundamental=None, technical=None),
        model_version="test",
    )


@pytest.mark.asyncio
async def test_notify_execution_skip_publishes_rejected_event() -> None:
    bus = AsyncMock()
    engine = ExecutionEngine(config=AppConfig(), bus=bus)
    signal = _trade_signal()

    await engine._notify_execution_skip(signal, "Risk rejected: max positions")

    bus.publish.assert_awaited_once()
    channel, event = bus.publish.await_args.args
    assert channel == BusChannel.ORDER_EVENT
    assert event.event_type == "rejected"
    assert event.detail == "Risk rejected: max positions"
    assert event.order.instrument == Instrument.EURUSD