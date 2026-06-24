"""Build live and final analytics payloads for manual replay sessions."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from src.backtest.scorer import ReplayScorer
from src.core.contracts import Instrument


def _trade_to_dict(trade: Any) -> dict[str, Any]:
    entry_time = getattr(trade, "entry_time", None)
    exit_time = getattr(trade, "exit_time", None)
    return {
        "entry_time": entry_time.isoformat() if hasattr(entry_time, "isoformat") else str(entry_time),
        "exit_time": exit_time.isoformat() if hasattr(exit_time, "isoformat") else str(exit_time),
        "entry_price": float(getattr(trade, "entry_price", 0.0)),
        "exit_price": float(getattr(trade, "exit_price", 0.0)),
        "size": float(getattr(trade, "size", 0.0)),
        "side": str(getattr(trade, "side", "")),
        "pnl": float(getattr(trade, "pnl", 0.0)),
        "pnl_pct": float(getattr(trade, "pnl_pct", 0.0)),
        "commission": float(getattr(trade, "commission", 0.0)),
    }


def build_manual_session_analytics(
    *,
    trade_history: list[Any],
    equity_history: list[tuple[datetime, float]],
    initial_capital: float,
    instrument: Instrument,
    start_date: datetime,
    current_time: datetime | None,
    open_positions_count: int = 0,
    session_status: str = "running",
) -> dict[str, Any]:
    """Score the session and attach trade log + equity series for the analytics UI."""
    if equity_history:
        times, values = zip(*equity_history)
        equity_curve = pd.Series(values, index=pd.to_datetime(times))
    else:
        equity_curve = pd.Series([initial_capital], index=pd.to_datetime([start_date]))

    metrics = ReplayScorer.calculate_metrics(
        trades=trade_history,
        equity_curve=equity_curve,
        initial_capital=initial_capital,
    )

    trades = [_trade_to_dict(t) for t in trade_history]
    wins = sum(1 for t in trades if t["pnl"] > 0)
    losses = sum(1 for t in trades if t["pnl"] < 0)
    gross_win = sum(t["pnl"] for t in trades if t["pnl"] > 0)
    gross_loss = abs(sum(t["pnl"] for t in trades if t["pnl"] < 0))
    avg_win = gross_win / wins if wins else 0.0
    avg_loss = gross_loss / losses if losses else 0.0
    best_trade = max((t["pnl"] for t in trades), default=0.0)
    worst_trade = min((t["pnl"] for t in trades), default=0.0)

    # Collapse duplicate timestamps — lightweight-charts requires strictly ascending unique times.
    equity_by_ts: dict[datetime, float] = {}
    for ts, eq in equity_history:
        dt = pd.to_datetime(ts).to_pydatetime() if not isinstance(ts, datetime) else ts
        equity_by_ts[dt] = float(eq)

    equity_points = [
        {
            "time": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
            "equity": value,
        }
        for ts, value in sorted(equity_by_ts.items(), key=lambda item: item[0])
    ]

    if not equity_points:
        equity_points = [
            {
                "time": start_date.isoformat() if hasattr(start_date, "isoformat") else str(start_date),
                "equity": float(initial_capital),
            }
        ]

    return {
        **metrics,
        "trades": trades,
        "equity_curve": equity_points,
        "trade_pnls": [{"index": i + 1, "pnl": t["pnl"], "side": t["side"]} for i, t in enumerate(trades)],
        "summary": {
            "wins": wins,
            "losses": losses,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "best_trade": best_trade,
            "worst_trade": worst_trade,
            "gross_profit": gross_win,
            "gross_loss": gross_loss,
        },
        "instrument": instrument.value,
        "open_positions": open_positions_count,
        "session_status": session_status,
        "current_time": current_time.isoformat() if current_time and hasattr(current_time, "isoformat") else None,
    }