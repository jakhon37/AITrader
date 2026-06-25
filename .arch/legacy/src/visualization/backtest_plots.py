"""Backtest visualization plots.

Creates equity curves, drawdown charts, and performance visualizations.
"""

import logging
from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from backtest.engine import BacktestResult
from backtest.metrics import calculate_drawdown_series, calculate_monthly_returns

logger = logging.getLogger(__name__)

# Set style
sns.set_style("darkgrid")
plt.rcParams["figure.figsize"] = (12, 6)
plt.rcParams["font.size"] = 10


def plot_equity_curve(
    result: BacktestResult,
    benchmark: Optional[pd.Series] = None,
    title: str = "Equity Curve",
    save_path: Optional[Path] = None,
) -> plt.Figure:
    """Plot equity curve over time.

    Args:
        result: BacktestResult with equity curve
        benchmark: Optional benchmark returns to compare
        title: Plot title
        save_path: Path to save figure (if None, displays only)

    Returns:
        Matplotlib figure
    """
    fig, ax = plt.subplots(figsize=(14, 7))

    # Plot strategy equity
    equity = result.equity_curve
    ax.plot(equity.index, equity.values, label="Strategy", linewidth=2, color="#2E86AB")

    # Plot benchmark if provided
    if benchmark is not None:
        benchmark_equity = result.config.initial_capital * (1 + benchmark.cumsum())
        ax.plot(
            benchmark_equity.index,
            benchmark_equity.values,
            label="Benchmark",
            linewidth=2,
            linestyle="--",
            color="#A23B72",
            alpha=0.7,
        )

    # Highlight trade periods
    for trade in result.trades:
        if trade.pnl > 0:
            color = "green"
            alpha = 0.1
        else:
            color = "red"
            alpha = 0.1
        ax.axvspan(trade.entry_time, trade.exit_time, color=color, alpha=alpha)

    # Format
    ax.set_xlabel("Date", fontsize=12, fontweight="bold")
    ax.set_ylabel("Equity ($)", fontsize=12, fontweight="bold")
    ax.set_title(title, fontsize=14, fontweight="bold", pad=20)
    ax.legend(loc="best", fontsize=11)
    ax.grid(True, alpha=0.3)

    # Add statistics box
    total_return = (equity.iloc[-1] - equity.iloc[0]) / equity.iloc[0]
    textstr = f"Initial: ${result.config.initial_capital:,.0f}\n"
    textstr += f"Final: ${equity.iloc[-1]:,.0f}\n"
    textstr += f"Return: {total_return:.2%}\n"
    textstr += f"Trades: {len(result.trades)}"

    props = dict(boxstyle="round", facecolor="wheat", alpha=0.8)
    ax.text(
        0.02,
        0.98,
        textstr,
        transform=ax.transAxes,
        fontsize=10,
        verticalalignment="top",
        bbox=props,
    )

    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=300, bbox_inches="tight")
        logger.info(f"Saved equity curve to {save_path}")

    return fig


def plot_drawdown(
    result: BacktestResult,
    title: str = "Drawdown",
    save_path: Optional[Path] = None,
) -> plt.Figure:
    """Plot drawdown over time.

    Args:
        result: BacktestResult with equity curve
        title: Plot title
        save_path: Path to save figure

    Returns:
        Matplotlib figure
    """
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True)

    equity = result.equity_curve
    drawdown = calculate_drawdown_series(equity)

    # Plot 1: Equity with drawdown shading
    ax1.plot(equity.index, equity.values, label="Equity", linewidth=2, color="#2E86AB")
    ax1.fill_between(
        equity.index,
        equity.values,
        equity.expanding().max(),
        where=(equity < equity.expanding().max()),
        color="red",
        alpha=0.2,
        label="Drawdown Period",
    )

    ax1.set_ylabel("Equity ($)", fontsize=12, fontweight="bold")
    ax1.set_title(title, fontsize=14, fontweight="bold", pad=20)
    ax1.legend(loc="best", fontsize=11)
    ax1.grid(True, alpha=0.3)

    # Plot 2: Drawdown percentage
    ax2.fill_between(
        drawdown.index,
        0,
        drawdown.values * 100,
        color="red",
        alpha=0.6,
        label="Drawdown %",
    )
    ax2.plot(drawdown.index, drawdown.values * 100, color="darkred", linewidth=1.5)

    # Mark max drawdown
    max_dd_idx = drawdown.idxmin()
    max_dd = drawdown.min()
    ax2.scatter(
        [max_dd_idx],
        [max_dd * 100],
        color="darkred",
        s=100,
        zorder=5,
        label=f"Max DD: {max_dd:.2%}",
    )

    ax2.set_xlabel("Date", fontsize=12, fontweight="bold")
    ax2.set_ylabel("Drawdown (%)", fontsize=12, fontweight="bold")
    ax2.legend(loc="best", fontsize=11)
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=300, bbox_inches="tight")
        logger.info(f"Saved drawdown plot to {save_path}")

    return fig


def plot_returns_distribution(
    result: BacktestResult,
    title: str = "Returns Distribution",
    save_path: Optional[Path] = None,
) -> plt.Figure:
    """Plot distribution of returns.

    Args:
        result: BacktestResult with returns
        title: Plot title
        save_path: Path to save figure

    Returns:
        Matplotlib figure
    """
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    returns = result.returns * 100  # Convert to percentage

    # Plot 1: Histogram with KDE
    ax1.hist(
        returns,
        bins=50,
        density=True,
        alpha=0.7,
        color="#2E86AB",
        edgecolor="black",
        label="Returns",
    )

    # Fit normal distribution
    mu, sigma = returns.mean(), returns.std()
    x = np.linspace(returns.min(), returns.max(), 100)
    ax1.plot(
        x,
        1 / (sigma * np.sqrt(2 * np.pi)) * np.exp(-0.5 * ((x - mu) / sigma) ** 2),
        "r-",
        linewidth=2,
        label=f"Normal(μ={mu:.3f}, σ={sigma:.3f})",
    )

    ax1.axvline(0, color="black", linestyle="--", linewidth=1, alpha=0.5)
    ax1.axvline(mu, color="red", linestyle="--", linewidth=1.5, label=f"Mean: {mu:.3f}%")

    ax1.set_xlabel("Return (%)", fontsize=12, fontweight="bold")
    ax1.set_ylabel("Density", fontsize=12, fontweight="bold")
    ax1.set_title("Return Distribution", fontsize=12, fontweight="bold")
    ax1.legend(fontsize=9)
    ax1.grid(True, alpha=0.3)

    # Plot 2: Box plot
    box = ax2.boxplot(
        [returns],
        labels=["Returns"],
        patch_artist=True,
        widths=0.5,
        medianprops=dict(color="red", linewidth=2),
        boxprops=dict(facecolor="#2E86AB", alpha=0.7),
    )

    # Add statistics
    stats_text = f"Mean: {mu:.3f}%\n"
    stats_text += f"Std: {sigma:.3f}%\n"
    stats_text += f"Median: {returns.median():.3f}%\n"
    stats_text += f"Min: {returns.min():.3f}%\n"
    stats_text += f"Max: {returns.max():.3f}%\n"
    stats_text += f"Skew: {returns.skew():.3f}\n"
    stats_text += f"Kurtosis: {returns.kurtosis():.3f}"

    props = dict(boxstyle="round", facecolor="wheat", alpha=0.8)
    ax2.text(
        1.5,
        0.5,
        stats_text,
        transform=ax2.transData,
        fontsize=9,
        verticalalignment="center",
        bbox=props,
    )

    ax2.set_ylabel("Return (%)", fontsize=12, fontweight="bold")
    ax2.set_title("Return Statistics", fontsize=12, fontweight="bold")
    ax2.grid(True, alpha=0.3, axis="y")

    fig.suptitle(title, fontsize=14, fontweight="bold", y=1.02)
    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=300, bbox_inches="tight")
        logger.info(f"Saved returns distribution to {save_path}")

    return fig


def plot_monthly_returns_heatmap(
    result: BacktestResult,
    title: str = "Monthly Returns Heatmap",
    save_path: Optional[Path] = None,
) -> plt.Figure:
    """Plot monthly returns as a heatmap.

    Args:
        result: BacktestResult with equity curve
        title: Plot title
        save_path: Path to save figure

    Returns:
        Matplotlib figure
    """
    fig, ax = plt.subplots(figsize=(14, 8))

    monthly_returns = calculate_monthly_returns(result.equity_curve)

    # Convert to percentage
    monthly_returns = monthly_returns * 100

    # Create heatmap
    sns.heatmap(
        monthly_returns,
        annot=True,
        fmt=".2f",
        cmap="RdYlGn",
        center=0,
        linewidths=0.5,
        cbar_kws={"label": "Return (%)"},
        ax=ax,
    )

    ax.set_title(title, fontsize=14, fontweight="bold", pad=20)
    ax.set_xlabel("Month", fontsize=12, fontweight="bold")
    ax.set_ylabel("Year", fontsize=12, fontweight="bold")

    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=300, bbox_inches="tight")
        logger.info(f"Saved monthly returns heatmap to {save_path}")

    return fig


def plot_trade_analysis(
    result: BacktestResult,
    title: str = "Trade Analysis",
    save_path: Optional[Path] = None,
) -> plt.Figure:
    """Plot trade-by-trade analysis.

    Args:
        result: BacktestResult with trades
        title: Plot title
        save_path: Path to save figure

    Returns:
        Matplotlib figure
    """
    if len(result.trades) == 0:
        logger.warning("No trades to plot")
        return None

    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(14, 10))

    trades = result.trades

    # Plot 1: Cumulative PnL
    cumulative_pnl = np.cumsum([t.pnl for t in trades])
    ax1.plot(range(1, len(trades) + 1), cumulative_pnl, marker="o", linewidth=2)
    ax1.axhline(0, color="black", linestyle="--", alpha=0.3)
    ax1.fill_between(
        range(1, len(trades) + 1),
        0,
        cumulative_pnl,
        where=(np.array(cumulative_pnl) >= 0),
        color="green",
        alpha=0.3,
    )
    ax1.fill_between(
        range(1, len(trades) + 1),
        0,
        cumulative_pnl,
        where=(np.array(cumulative_pnl) < 0),
        color="red",
        alpha=0.3,
    )
    ax1.set_xlabel("Trade #", fontweight="bold")
    ax1.set_ylabel("Cumulative PnL ($)", fontweight="bold")
    ax1.set_title("Cumulative PnL", fontweight="bold")
    ax1.grid(True, alpha=0.3)

    # Plot 2: Trade PnL distribution
    pnls = [t.pnl for t in trades]
    colors = ["green" if p > 0 else "red" for p in pnls]
    ax2.bar(range(1, len(trades) + 1), pnls, color=colors, alpha=0.7)
    ax2.axhline(0, color="black", linestyle="--", alpha=0.3)
    ax2.set_xlabel("Trade #", fontweight="bold")
    ax2.set_ylabel("PnL ($)", fontweight="bold")
    ax2.set_title("Individual Trade PnL", fontweight="bold")
    ax2.grid(True, alpha=0.3)

    # Plot 3: Holding period distribution
    holding_periods = [(t.exit_time - t.entry_time).days for t in trades]
    ax3.hist(holding_periods, bins=20, color="#2E86AB", alpha=0.7, edgecolor="black")
    ax3.axvline(
        np.mean(holding_periods),
        color="red",
        linestyle="--",
        linewidth=2,
        label=f"Mean: {np.mean(holding_periods):.1f} days",
    )
    ax3.set_xlabel("Holding Period (days)", fontweight="bold")
    ax3.set_ylabel("Frequency", fontweight="bold")
    ax3.set_title("Holding Period Distribution", fontweight="bold")
    ax3.legend()
    ax3.grid(True, alpha=0.3)

    # Plot 4: Win/Loss statistics
    wins = [t.pnl for t in trades if t.pnl > 0]
    losses = [t.pnl for t in trades if t.pnl < 0]

    categories = ["Wins", "Losses"]
    counts = [len(wins), len(losses)]
    colors_bar = ["green", "red"]

    ax4.bar(categories, counts, color=colors_bar, alpha=0.7)
    ax4.set_ylabel("Count", fontweight="bold")
    ax4.set_title(
        f"Win/Loss Ratio: {len(wins)}/{len(losses)} "
        f"({len(wins)/(len(wins)+len(losses))*100:.1f}%)",
        fontweight="bold",
    )
    ax4.grid(True, alpha=0.3, axis="y")

    # Add value labels on bars
    for i, (cat, count) in enumerate(zip(categories, counts)):
        ax4.text(i, count, str(count), ha="center", va="bottom", fontweight="bold")

    fig.suptitle(title, fontsize=14, fontweight="bold", y=0.995)
    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=300, bbox_inches="tight")
        logger.info(f"Saved trade analysis to {save_path}")

    return fig
