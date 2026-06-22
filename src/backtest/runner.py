"""Command-line entry point and session coordinator for D08-BACKTEST.

Supports automated backtesting using EventDrivenBacktestEngine and DataFeed
across multiple timeframes on an isolated InProcessBus.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import sys
from typing import Any
import numpy as np
import pandas as pd

from src.core.bus import InProcessBus
from src.core.clock import ReplayClock, set_clock
from src.core.contracts import Instrument, Timeframe
from src.core.config import load_instruments
from src.data.store import DataStore
from src.technical.engine import TechnicalEngine
from src.backtest.feed import DataFeed
from src.backtest.engine import EventDrivenBacktestEngine


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="AITrader Backtest Runner")
    parser.add_argument(
        "--mode",
        choices=["auto", "replay", "manual"],
        default="auto",
        help="Backtest mode (auto is default for Phase 2a)",
    )
    parser.add_argument(
        "--instrument",
        default="EURUSD",
        help="Trading instrument (e.g. EURUSD, GBPUSD)",
    )
    parser.add_argument(
        "--start",
        default="2022-01-01",
        help="Start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end",
        default="2022-12-31",
        help="End date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=10000.0,
        help="Initial capital in USD",
    )
    parser.add_argument(
        "--causal",
        action="store_true",
        help="Enable dynamic Granger causality filtering on technical indicators",
    )
    return parser.parse_args()


def calculate_metrics(
    trades: list[Any],
    equity_curve: pd.Series,
    initial_capital: float,
) -> dict[str, Any]:
    """Calculate standard performance metrics from trades and equity curve."""
    final_equity = float(equity_curve.iloc[-1])
    net_profit = final_equity - initial_capital
    net_profit_pct = (net_profit / initial_capital) * 100.0

    total_trades = len(trades)
    wins = [t for t in trades if t.pnl > 0]
    win_rate = (len(wins) / total_trades * 100.0) if total_trades > 0 else 0.0

    gross_profit = sum(t.pnl for t in trades if t.pnl > 0)
    gross_loss = abs(sum(t.pnl for t in trades if t.pnl < 0))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf") if gross_profit > 0 else 1.0

    # Sharpe Ratio (daily return estimate)
    returns = equity_curve.pct_change().dropna()
    if len(returns) > 1 and returns.std() > 0:
        sharpe = (returns.mean() / returns.std()) * np.sqrt(252)
    else:
        sharpe = 0.0

    # Max Drawdown
    rolling_max = equity_curve.cummax()
    drawdowns = (equity_curve - rolling_max) / rolling_max
    max_dd = drawdowns.min() * 100.0  # Percentage

    return {
        "final_equity": final_equity,
        "net_profit": net_profit,
        "net_profit_pct": net_profit_pct,
        "total_trades": total_trades,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "sharpe": sharpe,
        "max_dd": max_dd,
    }


def print_report(metrics: dict[str, Any], start_str: str, end_str: str) -> None:
    """Print backtest results to console."""
    print("=" * 60)
    print("                 AITRADER BACKTEST REPORT")
    print(f" Period: {start_str} to {end_str}")
    print("=" * 60)
    print(f" Final Equity:          ${metrics['final_equity']:.2f}")
    print(f" Net Profit:            ${metrics['net_profit']:.2f} ({metrics['net_profit_pct']:.2f}%)")
    print(f" Total Trades:          {metrics['total_trades']}")
    print(f" Win Rate:              {metrics['win_rate']:.2f}%")
    print(f" Profit Factor:         {metrics['profit_factor']:.2f}")
    print(f" Sharpe Ratio:          {metrics['sharpe']:.2f}")
    print(f" Max Drawdown:          {metrics['max_dd']:.2f}%")
    print("=" * 60)


async def main_async() -> None:
    args = parse_args()

    # Parse dates
    try:
        start_date = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end_date = datetime.strptime(args.end, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
    except ValueError as e:
        print(f"Error parsing dates: {e}")
        sys.exit(1)

    instrument = Instrument(args.instrument)

    # 1. Setup Replay Clock
    clock = ReplayClock(start_date)
    set_clock(clock)

    # 2. Isolated Replay Bus
    bus = InProcessBus()

    # 3. Data Store
    store = DataStore()

    # 4. Instantiate Technical Engine
    inst_configs = load_instruments()
    if instrument not in inst_configs:
        print(f"Instrument {instrument.value} not found in configurations.")
        sys.exit(1)

    tech_engine = TechnicalEngine(
        bus=bus,
        store=store,
        instruments_config=inst_configs,
        enable_causal_filter=args.causal,
    )

    # 5. Instantiate Data Feed
    tf_config = inst_configs[instrument]
    feed = DataFeed(
        store=store,
        instrument=instrument,
        timeframes=tf_config.active_timeframes,
        start=start_date,
        end=end_date,
        clock=clock,
    )

    # 6. Event Driven Engine
    print(f"Running automated backtest for {instrument.value}...")
    engine = EventDrivenBacktestEngine(initial_capital=args.capital)

    trades, equity_curve = await engine.run(feed, bus, tech_engine)

    # Calculate and show report
    metrics = calculate_metrics(trades, equity_curve, args.capital)
    print_report(metrics, args.start, args.end)


def main() -> None:
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\nBacktest cancelled by user.")
        sys.exit(0)


if __name__ == "__main__":
    main()
