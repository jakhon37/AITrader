"""Walk-forward validation for backtesting."""

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from backtest.engine import BacktestConfig, BacktestEngine, BacktestResult
from backtest.metrics import PerformanceMetrics, calculate_metrics

logger = logging.getLogger(__name__)


@dataclass
class WalkForwardConfig:
    """Configuration for walk-forward validation."""

    train_period: int = 252  # Trading days for training
    test_period: int = 63  # Trading days for testing (1 quarter)
    step_size: int = 21  # Days to step forward (1 month)
    min_train_samples: int = 100  # Minimum samples required


@dataclass
class WalkForwardWindow:
    """Single walk-forward window."""

    window_id: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    train_size: int
    test_size: int
    result: Optional[BacktestResult] = None
    metrics: Optional[PerformanceMetrics] = None


@dataclass
class WalkForwardResult:
    """Results from walk-forward validation."""

    windows: list[WalkForwardWindow]
    config: WalkForwardConfig
    backtest_config: BacktestConfig
    summary_metrics: dict


class WalkForwardValidator:
    """Walk-forward validation engine."""

    def __init__(
        self,
        wf_config: Optional[WalkForwardConfig] = None,
        backtest_config: Optional[BacktestConfig] = None,
    ) -> None:
        """Initialize validator."""
        self.wf_config = wf_config or WalkForwardConfig()
        self.backtest_config = backtest_config or BacktestConfig()
        logger.info(
            f"Walk-forward: train={self.wf_config.train_period}, "
            f"test={self.wf_config.test_period}, step={self.wf_config.step_size}"
        )

    def generate_windows(self, data: pd.DataFrame) -> list[WalkForwardWindow]:
        """Generate walk-forward windows."""
        windows = []
        window_id = 0

        start_idx = 0
        while True:
            train_end_idx = start_idx + self.wf_config.train_period
            if train_end_idx >= len(data):
                break

            test_start_idx = train_end_idx
            test_end_idx = test_start_idx + self.wf_config.test_period
            if test_end_idx > len(data):
                break

            if train_end_idx - start_idx < self.wf_config.min_train_samples:
                break

            window = WalkForwardWindow(
                window_id=window_id,
                train_start=data.index[start_idx],
                train_end=data.index[train_end_idx - 1],
                test_start=data.index[test_start_idx],
                test_end=data.index[test_end_idx - 1],
                train_size=train_end_idx - start_idx,
                test_size=test_end_idx - test_start_idx,
            )
            windows.append(window)

            start_idx += self.wf_config.step_size
            window_id += 1

        logger.info(f"Generated {len(windows)} walk-forward windows")
        return windows

    def run(
        self, data: pd.DataFrame, signals: pd.Series, retrain_fn: Optional[callable] = None
    ) -> WalkForwardResult:
        """Run walk-forward validation."""
        logger.info("Starting walk-forward validation")

        windows = self.generate_windows(data)
        if len(windows) == 0:
            raise ValueError("No valid walk-forward windows")

        engine = BacktestEngine(self.backtest_config)

        for window in windows:
            logger.info(
                f"Window {window.window_id}: "
                f"{window.test_start.date()} to {window.test_end.date()}"
            )

            test_data = data.loc[window.test_start : window.test_end]
            test_signals = signals.loc[window.test_start : window.test_end]

            if retrain_fn is not None:
                train_data = data.loc[window.train_start : window.train_end]
                test_signals = retrain_fn(train_data, test_data)

            result = engine.run(test_data, test_signals)
            metrics = calculate_metrics(result)

            window.result = result
            window.metrics = metrics

            logger.info(
                f"Window {window.window_id}: Sharpe={metrics.sharpe_ratio:.2f}, "
                f"Return={metrics.total_return:.2%}"
            )

        summary = self._calculate_summary(windows)

        result = WalkForwardResult(
            windows=windows,
            config=self.wf_config,
            backtest_config=self.backtest_config,
            summary_metrics=summary,
        )

        logger.info(f"Walk-forward complete: {len(windows)} windows")
        return result

    def _calculate_summary(self, windows: list[WalkForwardWindow]) -> dict:
        """Calculate summary metrics."""
        sharpes = [w.metrics.sharpe_ratio for w in windows]
        returns = [w.metrics.total_return for w in windows]
        max_dds = [w.metrics.max_drawdown for w in windows]
        win_rates = [w.metrics.win_rate for w in windows]
        total_trades = [w.metrics.total_trades for w in windows]

        # Collect all equity curves and concatenate at once to avoid FutureWarning
        equity_curves = [window.result.equity_curve for window in windows]
        combined_equity = pd.concat(equity_curves) if equity_curves else pd.Series(dtype=float)

        total_return = (
            combined_equity.iloc[-1] - combined_equity.iloc[0]
        ) / combined_equity.iloc[0]

        return {
            "num_windows": len(windows),
            "avg_sharpe": np.mean(sharpes),
            "median_sharpe": np.median(sharpes),
            "min_sharpe": np.min(sharpes),
            "max_sharpe": np.max(sharpes),
            "std_sharpe": np.std(sharpes),
            "avg_return": np.mean(returns),
            "median_return": np.median(returns),
            "total_return": total_return,
            "avg_max_dd": np.mean(max_dds),
            "worst_dd": np.min(max_dds),
            "avg_win_rate": np.mean(win_rates),
            "total_trades": sum(total_trades),
            "avg_trades_per_window": np.mean(total_trades),
            "positive_windows": sum(1 for r in returns if r > 0),
            "negative_windows": sum(1 for r in returns if r <= 0),
            "positive_sharpe_windows": sum(1 for s in sharpes if s > 0),
        }


def print_walk_forward_summary(result: WalkForwardResult) -> None:
    """Print walk-forward summary."""
    print("\n" + "=" * 70)
    print("WALK-FORWARD VALIDATION RESULTS")
    print("=" * 70)

    print(f"\nConfiguration:")
    print(f"  Training Period:    {result.config.train_period} days")
    print(f"  Testing Period:     {result.config.test_period} days")
    print(f"  Step Size:          {result.config.step_size} days")
    print(f"  Total Windows:      {result.summary_metrics['num_windows']}")

    print(f"\nSharpe Ratio:")
    print(f"  Average:            {result.summary_metrics['avg_sharpe']:>10.2f}")
    print(f"  Median:             {result.summary_metrics['median_sharpe']:>10.2f}")
    print(f"  Std Dev:            {result.summary_metrics['std_sharpe']:>10.2f}")
    print(f"  Min:                {result.summary_metrics['min_sharpe']:>10.2f}")
    print(f"  Max:                {result.summary_metrics['max_sharpe']:>10.2f}")

    print(f"\nReturns:")
    print(f"  Average:            {result.summary_metrics['avg_return']:>10.2%}")
    print(f"  Total:              {result.summary_metrics['total_return']:>10.2%}")
    print(
        f"  Positive Windows:   {result.summary_metrics['positive_windows']} / "
        f"{result.summary_metrics['num_windows']}"
    )

    print(f"\nDrawdown:")
    print(f"  Average Max DD:     {result.summary_metrics['avg_max_dd']:>10.2%}")
    print(f"  Worst DD:           {result.summary_metrics['worst_dd']:>10.2%}")

    print(f"\nTrades:")
    print(f"  Total:              {result.summary_metrics['total_trades']:>10}")
    print(f"  Avg per Window:     {result.summary_metrics['avg_trades_per_window']:>10.1f}")
    print(f"  Avg Win Rate:       {result.summary_metrics['avg_win_rate']:>10.2%}")

    print("\n" + "=" * 70 + "\n")
