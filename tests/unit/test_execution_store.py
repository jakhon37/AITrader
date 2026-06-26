"""Unit tests for D06 execution SQLite store."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.core.contracts import (
    ExecutionMode,
    Instrument,
    Order,
    OrderEvent,
    OrderSide,
    OrderStatus,
    PortfolioState,
    PositionSummary,
)
from src.execution.store import ExecutionStore


def _portfolio(
    *,
    balance: float = 100_000.0,
    positions: list[PositionSummary] | None = None,
) -> PortfolioState:
    positions = positions or []
    equity = balance + sum(p.unrealized_pnl for p in positions)
    return PortfolioState(
        signal_id="test-signal",
        timestamp=datetime(2026, 6, 26, 12, 0, tzinfo=timezone.utc),
        execution_mode=ExecutionMode.PAPER,
        balance=balance,
        equity=equity,
        margin_used=0.0,
        free_margin=equity,
        open_positions=positions,
        realized_pnl_today=125.5,
        drawdown_pct=0.01,
    )


def test_save_and_load_portfolio_snapshot(tmp_path: Path) -> None:
    store = ExecutionStore(tmp_path / "execution.db")
    pos = PositionSummary(
        instrument=Instrument.EURUSD,
        side=OrderSide.BUY,
        size=0.5,
        entry_price=1.10,
        current_price=1.105,
        unrealized_pnl=250.0,
        open_since=datetime(2026, 6, 26, 10, 0, tzinfo=timezone.utc),
    )
    state = _portfolio(balance=99_000.0, positions=[pos])

    store.save_portfolio_snapshot(state, initial_capital=100_000.0, total_realized_pnl=500.0)

    loaded = store.get_latest_portfolio()
    assert loaded is not None
    assert loaded.balance == 99_000.0
    assert loaded.realized_pnl_today == 125.5
    assert len(loaded.open_positions) == 1
    assert loaded.open_positions[0].instrument == Instrument.EURUSD


def test_order_event_and_closed_trade_persist(tmp_path: Path) -> None:
    store = ExecutionStore(tmp_path / "execution.db")
    order = Order(
        order_id="ord-1",
        signal_id="sig-1",
        instrument=Instrument.EURUSD,
        side=OrderSide.BUY,
        size=1.0,
        order_type="market",
        limit_price=None,
        stop_price=None,
        sl=None,
        tp=None,
        status=OrderStatus.FILLED,
        created_at=datetime(2026, 6, 26, 12, 0, tzinfo=timezone.utc),
        filled_at=datetime(2026, 6, 26, 12, 1, tzinfo=timezone.utc),
        filled_price=1.101,
        execution_mode=ExecutionMode.PAPER,
    )
    event = OrderEvent(
        signal_id="sig-1",
        event_type="filled",
        order=order,
        timestamp=datetime(2026, 6, 26, 12, 1, tzinfo=timezone.utc),
    )
    store.save_order_event(event)

    store.record_closed_trade(
        signal_id="sig-1",
        instrument=Instrument.EURUSD,
        side=OrderSide.BUY,
        size=1.0,
        entry_price=1.10,
        exit_price=1.101,
        realized_pnl=100.0,
        opened_at=datetime(2026, 6, 26, 11, 0, tzinfo=timezone.utc),
        closed_at=datetime(2026, 6, 26, 12, 1, tzinfo=timezone.utc),
    )

    orders = store.list_order_events(limit=10)
    trades = store.list_closed_trades(limit=10)
    assert len(orders) == 1
    assert orders[0]["event_type"] == "filled"
    assert len(trades) == 1
    assert trades[0]["realized_pnl"] == 100.0


def test_import_legacy_positions_json(tmp_path: Path) -> None:
    legacy = tmp_path / "positions.json"
    legacy.write_text(
        json.dumps(
            {
                "cash": 110_393.92,
                "initial_capital": 100_000.0,
                "total_realized_pnl": 5201.57,
                "realized_pnl_today": 5201.57,
                "peak_equity": 110_396.25,
                "positions": {},
            }
        )
    )
    store = ExecutionStore(tmp_path / "execution.db")
    assert store.import_legacy_positions_json(legacy) is True

    loaded = store.get_latest_portfolio()
    assert loaded is not None
    assert loaded.balance == 110_393.92
    assert loaded.open_positions == []
    assert store.import_legacy_positions_json(legacy) is False