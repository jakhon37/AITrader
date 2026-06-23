"""Vectorized backtesting engine for D08-BACKTEST."""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

from src.backtest.engine.contracts import BacktestConfig, BacktestResult, Trade

logger = logging.getLogger(__name__)


class BacktestEngine:
    """Vectorized backtesting engine.

    Supports:
    - Long and short positions
    - Transaction costs and slippage
    - Position sizing
    - Realistic trade execution
    """

    def __init__(self, config: Optional[BacktestConfig] = None) -> None:
        """Initialize backtesting engine.

        Args:
            config: Backtest configuration
        """
        self.config = config or BacktestConfig()
        logger.info(f"Initialized backtest engine with config: {self.config}")

    def run(
        self,
        data: pd.DataFrame,
        signals: pd.Series,
        position_sizes: Optional[pd.Series] = None,
    ) -> BacktestResult:
        """Run backtest on historical data.

        Args:
            data: DataFrame with OHLCV data (must have 'close' column)
            signals: Series with trading signals (1=long, -1=short, 0=neutral)
            position_sizes: Optional position sizes (default: config.position_size_pct)

        Returns:
            BacktestResult with trades, equity curve, and performance metrics
        """
        logger.info(f"Starting backtest on {len(data)} bars")

        # Validate inputs
        if "close" not in data.columns:
            raise ValueError("Data must contain 'close' column")

        if len(signals) != len(data):
            raise ValueError("Signals must match data length")

        # Align signals with data
        signals = signals.reindex(data.index, fill_value=0)

        # Use default position sizes if not provided
        if position_sizes is None:
            position_sizes = pd.Series(
                self.config.position_size_pct, index=data.index
            )
        else:
            position_sizes = position_sizes.reindex(
                data.index, fill_value=self.config.position_size_pct
            )

        # Generate trades
        trades = self._generate_trades(data, signals, position_sizes)

        # Calculate equity curve
        equity_curve, positions, returns = self._calculate_equity_curve(
            data, trades
        )

        # Create result
        result = BacktestResult(
            trades=trades,
            equity_curve=equity_curve,
            positions=positions,
            returns=returns,
            config=self.config,
            metadata={
                "total_bars": len(data),
                "total_trades": len(trades),
                "start_date": data.index[0],
                "end_date": data.index[-1],
            },
        )

        logger.info(f"Backtest complete: {len(trades)} trades executed")
        return result

    def _generate_trades(
        self,
        data: pd.DataFrame,
        signals: pd.Series,
        position_sizes: pd.Series,
    ) -> list[Trade]:
        """Generate trades from signals."""
        trades = []
        current_position = None
        last_trade_idx = -np.inf

        prices = data["close"].values
        times = data.index

        for i, (time, signal) in enumerate(zip(times, signals)):
            # Check if we should enforce min trade interval
            if i - last_trade_idx < self.config.min_trade_interval:
                continue

            # Exit current position if signal changed or goes to neutral
            if current_position is not None:
                should_exit = (
                    signal == 0  # Signal goes neutral
                    or signal != current_position["side"]  # Signal reverses
                )

                if should_exit:
                    # Exit at current price with slippage
                    exit_price = self._apply_slippage(
                        prices[i], current_position["side"], is_entry=False
                    )

                    # Calculate PnL
                    if current_position["side"] == 1:  # Long
                        pnl = current_position["size"] * (
                            exit_price - current_position["entry_price"]
                        )
                    else:  # Short
                        pnl = current_position["size"] * (
                            current_position["entry_price"] - exit_price
                        )

                    # Subtract exit commission
                    commission = (
                        abs(current_position["size"] * exit_price)
                        * self.config.commission_pct
                    )
                    pnl -= commission

                    # Create trade record
                    trade = Trade(
                        entry_time=current_position["entry_time"],
                        exit_time=time,
                        entry_price=current_position["entry_price"],
                        exit_price=exit_price,
                        size=current_position["size"],
                        side="long" if current_position["side"] == 1 else "short",
                        pnl=pnl,
                        pnl_pct=pnl / self.config.initial_capital,
                        commission=commission,
                    )
                    trades.append(trade)
                    current_position = None
                    last_trade_idx = i

            # Enter new position if signal is non-zero and we have no position
            if current_position is None and signal in [1, -1]:
                # Calculate trade size based on capital
                capital = self.config.initial_capital
                if len(trades) > 0:
                    capital += sum(t.pnl for t in trades)

                # Limit position size
                trade_size_pct = position_sizes.iloc[i]
                position_value = capital * trade_size_pct
                entry_price = self._apply_slippage(prices[i], signal, is_entry=True)
                size = position_value / entry_price

                # Apply entry commission
                commission = position_value * self.config.commission_pct

                current_position = {
                    "entry_time": time,
                    "entry_price": entry_price,
                    "size": size,
                    "side": signal,
                    "commission": commission,
                }
                last_trade_idx = i

        # Force-close any open position on the last bar
        if current_position is not None:
            exit_price = self._apply_slippage(prices[-1], current_position["side"], is_entry=False)
            
            if current_position["side"] == 1:
                pnl = current_position["size"] * (exit_price - current_position["entry_price"])
            else:
                pnl = current_position["size"] * (current_position["entry_price"] - exit_price)

            commission = abs(current_position["size"] * exit_price) * self.config.commission_pct
            pnl -= commission

            trade = Trade(
                entry_time=current_position["entry_time"],
                exit_time=times[-1],
                entry_price=current_position["entry_price"],
                exit_price=exit_price,
                size=current_position["size"],
                side="long" if current_position["side"] == 1 else "short",
                pnl=pnl,
                pnl_pct=pnl / self.config.initial_capital,
                commission=commission,
            )
            trades.append(trade)

        return trades

    def _apply_slippage(
        self, price: float, side: int, is_entry: bool
    ) -> float:
        """Apply slippage to price."""
        multiplier = 1.0
        if is_entry:
            multiplier = 1.0 if side == 1 else -1.0
        else:
            multiplier = -1.0 if side == 1 else 1.0

        return price * (1.0 + multiplier * self.config.slippage_pct)

    def _calculate_equity_curve(
        self, data: pd.DataFrame, trades: list[Trade]
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate equity curve, position states, and returns."""
        capital = self.config.initial_capital
        equity = pd.Series(capital, index=data.index)
        positions = pd.Series(0, index=data.index)

        # Vectorized calculation of position weights
        for trade in trades:
            positions.loc[trade.entry_time : trade.exit_time] = (
                1 if trade.side == "long" else -1
            )

        # Step-by-step equity simulation
        for i in range(1, len(data)):
            current_time = data.index[i]
            prev_time = data.index[i - 1]

            # Calculate returns for active positions
            pos = positions.loc[prev_time]
            if pos != 0:
                ret = (data["close"].iloc[i] / data["close"].iloc[i - 1]) - 1.0
                capital_change = capital * pos * ret
                capital += capital_change

            # Update commissions and realized PnL at trade exit
            for trade in trades:
                if trade.exit_time == current_time:
                    pass

            equity.iloc[i] = capital

        returns = equity.pct_change().fillna(0.0)
        return equity, positions, returns
