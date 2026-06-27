"""Notifier /portfolio reads from execution database."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.contracts import ExecutionMode, PortfolioState
from src.execution.store import ExecutionStore
from src.notifier.commands import CommandProcessor


@pytest.mark.asyncio
async def test_portfolio_command_reads_from_execution_store(tmp_path: Path) -> None:
    store = ExecutionStore(tmp_path / "execution.db")
    store.save_portfolio_snapshot(
        PortfolioState(
            signal_id="db",
            timestamp=datetime(2026, 6, 26, 12, 0, tzinfo=timezone.utc),
            execution_mode=ExecutionMode.PAPER,
            balance=110_393.92,
            equity=110_393.92,
            margin_used=0.0,
            free_margin=110_393.92,
            open_positions=[],
            realized_pnl_today=5201.57,
            drawdown_pct=0.0,
        )
    )

    processor = CommandProcessor(
        bus=MagicMock(),
        config=MagicMock(core=MagicMock(execution_mode=ExecutionMode.PAPER)),
        execution_store=store,
    )
    sent: list[str] = []

    async def capture(msg: str) -> None:
        sent.append(msg)

    await processor._cmd_portfolio(capture)

    assert len(sent) == 1
    assert "110,393.92" in sent[0]
    assert "Active Positions:</b> 0" in sent[0]