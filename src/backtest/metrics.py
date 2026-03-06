"""Performance metrics for backtesting.

Calculates standard trading performance metrics including
Sharpe ratio, Sortino ratio, max drawdown, win rate, etc.
"""

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from backtest.engine import BacktestResult

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Complete performance metrics for a backtest."""

    # Returns metrics
    total_return: float
    annualized_return: float
    volatility: float
    downside_deviation: float

    # Risk-adjusted metrics
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float

    # Drawdown metrics
    max_drawdown: float
    max_drawdown_duration: int  # in days
    avg_drawdown: float

    # Trade metrics
    total_trades: int
    win_rate: float
    profit_factor: float
    avg_win: float
    avg_loss: float
    avg_trade: float
    best_trade: float
    worst_trade: float

    # Holding periods
    avg_holding_period: float  # in days
    max_holding_period: int
    min_holding_period: int

    # Other
    total_commission: float


def calculate_metrics(
    result: BacktestResult,
    risk_free_rate: float = 0.0,
    trading_days: int = 252,
) -> PerformanceMetrics:
    """Calculate all performance metrics from backtest result.

    Args:
        result: BacktestResult from backtesting engine
        risk_free_rate: Annual risk-free rate (default: 0.0)
        trading_days: Trading days per year (default: 252)

    Returns:
        PerformanceMetrics with all calculated metrics
    """
    logger.info("Calculating performance metrics")

    returns = result.returns
    equity = result.equity_curve
    trades = result.trades

    # Returns metrics
    total_return = (equity.iloc[-1] - equity.iloc[0]) / equity.iloc[0]
    periods = len(returns)
    years = periods / trading_days
    annualized_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0.0

    volatility = returns.std() * np.sqrt(trading_days)

    # Downside deviation (only negative returns)
    downside_returns = returns[returns < 0]
    downside_deviation = (
        downside_returns.std() * np.sqrt(trading_days)
        if len(downside_returns) > 0
        else 0.0
    )

    # Sharpe ratio
    excess_return = annualized_return - risk_free_rate
    sharpe_ratio = excess_return / volatility if volatility > 0 else 0.0

    # Sortino ratio
    sortino_ratio = (
        excess_return / downside_deviation if downside_deviation > 0 else 0.0
    )

    # Drawdown calculations
    dd_series = calculate_drawdown_series(equity)
    max_drawdown = dd_series.min()
    avg_drawdown = dd_series[dd_series < 0].mean() if (dd_series < 0).any() else 0.0

    # Max drawdown duration
    dd_duration = calculate_drawdown_duration(dd_series)
    max_dd_duration = dd_duration.max() if len(dd_duration) > 0 else 0

    # Calmar ratio
    calmar_ratio = (
        annualized_return / abs(max_drawdown) if max_drawdown < 0 else 0.0
    )

    # Trade statistics
    if len(trades) > 0:
        pnls = [t.pnl for t in trades]
        winning_trades = [p for p in pnls if p > 0]
        losing_trades = [p for p in pnls if p < 0]

        total_trades = len(trades)
        win_rate = len(winning_trades) / total_trades if total_trades > 0 else 0.0

        total_wins = sum(winning_trades) if winning_trades else 0.0
        total_losses = abs(sum(losing_trades)) if losing_trades else 0.0
        profit_factor = (
            total_wins / total_losses if total_losses > 0 else float("inf")
        )

        avg_win = np.mean(winning_trades) if winning_trades else 0.0
        avg_loss = np.mean(losing_trades) if losing_trades else 0.0
        avg_trade = np.mean(pnls)
        best_trade = max(pnls)
        worst_trade = min(pnls)

        # Holding periods
        holding_periods = [
            (t.exit_time - t.entry_time).days for t in trades
        ]
        avg_holding_period = np.mean(holding_periods)
        max_holding_period = max(holding_periods)
        min_holding_period = min(holding_periods)

        total_commission = sum(t.commission for t in trades)
    else:
        total_trades = 0
        win_rate = 0.0
        profit_factor = 0.0
        avg_win = 0.0
        avg_loss = 0.0
        avg_trade = 0.0
        best_trade = 0.0
        worst_trade = 0.0
        avg_holding_period = 0.0
        max_holding_period = 0
        min_holding_period = 0
        total_commission = 0.0

    metrics = PerformanceMetrics(
        total_return=total_return,
        annualized_return=annualized_return,
        volatility=volatility,
        downside_deviation=downside_deviation,
        sharpe_ratio=sharpe_ratio,
        sortino_ratio=sortino_ratio,
        calmar_ratio=calmar_ratio,
        max_drawdown=max_drawdown,
        max_drawdown_duration=max_dd_duration,
        avg_drawdown=avg_drawdown,
        total_trades=total_trades,
        win_rate=win_rate,
        profit_factor=profit_factor,
        avg_win=avg_win,
        avg_loss=avg_loss,
        avg_trade=avg_trade,
        best_trade=best_trade,
        worst_trade=worst_trade,
        avg_holding_period=avg_holding_period,
        max_holding_period=max_holding_period,
        min_holding_period=min_holding_period,
        total_commission=total_commission,
    )

    logger.info(
        f"Metrics calculated: Sharpe={metrics.sharpe_ratio:.2f}, "
        f"Max DD={metrics.max_drawdown:.2%}, Win Rate={metrics.win_rate:.2%}"
    )

    return metrics


def calculate_drawdown_series(equity: pd.Series) -> pd.Series:
    """Calculate drawdown series from equity curve.

    Args:
        equity: Equity curve

    Returns:
        Series of drawdowns (as fractions, negative values)
    """
    running_max = equity.expanding().max()
    drawdown = (equity - running_max) / running_max
    return drawdown


def calculate_drawdown_duration(drawdown: pd.Series) -> pd.Series:
    """Calculate duration of each drawdown period.

    Args:
        drawdown: Drawdown series

    Returns:
        Series of drawdown durations in days
    """
    is_drawdown = drawdown < 0
    drawdown_groups = (is_drawdown != is_drawdown.shift()).cumsum()

    durations = []
    for group_id in drawdown_groups[is_drawdown].unique():
        group_size = (drawdown_groups == group_id).sum()
        durations.append(group_size)

    return pd.Series(durations) if durations else pd.Series(dtype=int)


def calculate_rolling_sharpe(
    returns: pd.Series,
    window: int = 252,
    risk_free_rate: float = 0.0,
) -> pd.Series:
    """Calculate rolling Sharpe ratio.

    Args:
        returns: Return series
        window: Rolling window size (default: 252 trading days = 1 year)
        risk_free_rate: Annual risk-free rate

    Returns:
        Series of rolling Sharpe ratios
    """
    excess_returns = returns - risk_free_rate / 252  # Daily risk-free rate
    rolling_mean = excess_returns.rolling(window).mean() * 252
    rolling_std = excess_returns.rolling(window).std() * np.sqrt(252)

    rolling_sharpe = rolling_mean / rolling_std
    return rolling_sharpe.fillna(0.0)


def calculate_monthly_returns(equity: pd.Series) -> pd.DataFrame:
    """Calculate monthly returns from equity curve.

    Args:
        equity: Equity curve

    Returns:
        DataFrame with monthly returns (rows=years, columns=months)
    """
    # Resample to month-end
    monthly_equity = equity.resample("M").last()

    # Calculate monthly returns
    monthly_returns = monthly_equity.pct_change()

    # Pivot to year x month matrix
    monthly_returns_df = pd.DataFrame(
        {
            "year": monthly_returns.index.year,
            "month": monthly_returns.index.month,
            "return": monthly_returns.values,
        }
    )

    pivot = monthly_returns_df.pivot(
        index="year", columns="month", values="return"
    )

    # Rename columns to month names
    month_names = [
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    ]
    pivot.columns = [month_names[m - 1] for m in pivot.columns]

    return pivot


def print_metrics(metrics: PerformanceMetrics) -> None:
    """Print metrics in readable format.

    Args:
        metrics: Performance metrics to print
    """
    print("\n" + "=" * 60)
    print("PERFORMANCE METRICS")
    print("=" * 60)

    print("\nReturns:")
    print(f"  Total Return:       {metrics.total_return:>10.2%}")
    print(f"  Annualized Return:  {metrics.annualized_return:>10.2%}")
    print(f"  Volatility (ann):   {metrics.volatility:>10.2%}")

    print("\nRisk-Adjusted:")
    print(f"  Sharpe Ratio:       {metrics.sharpe_ratio:>10.2f}")
    print(f"  Sortino Ratio:      {metrics.sortino_ratio:>10.2f}")
    print(f"  Calmar Ratio:       {metrics.calmar_ratio:>10.2f}")

    print("\nDrawdown:")
    print(f"  Max Drawdown:       {metrics.max_drawdown:>10.2%}")
    print(f"  Max DD Duration:    {metrics.max_drawdown_duration:>10} days")
    print(f"  Avg Drawdown:       {metrics.avg_drawdown:>10.2%}")

    print("\nTrades:")
    print(f"  Total Trades:       {metrics.total_trades:>10}")
    print(f"  Win Rate:           {metrics.win_rate:>10.2%}")
    print(f"  Profit Factor:      {metrics.profit_factor:>10.2f}")
    print(f"  Avg Trade:          ${metrics.avg_trade:>9.2f}")
    print(f"  Avg Win:            ${metrics.avg_win:>9.2f}")
    print(f"  Avg Loss:           ${metrics.avg_loss:>9.2f}")
    print(f"  Best Trade:         ${metrics.best_trade:>9.2f}")
    print(f"  Worst Trade:        ${metrics.worst_trade:>9.2f}")

    print("\nHolding Periods:")
    print(f"  Average:            {metrics.avg_holding_period:>10.1f} days")
    print(f"  Maximum:            {metrics.max_holding_period:>10} days")
    print(f"  Minimum:            {metrics.min_holding_period:>10} days")

    print("\nCosts:")
    print(f"  Total Commission:   ${metrics.total_commission:>9.2f}")

    print("=" * 60 + "\n")
