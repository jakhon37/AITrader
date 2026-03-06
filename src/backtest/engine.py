"""Backtesting engine with vectorized calculations.

Simulates trading strategies on historical data with realistic
transaction costs and slippage modeling.
"""

import logging
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class BacktestConfig:
    """Configuration for backtesting."""

    initial_capital: float = 10000.0
    commission_pct: float = 0.001  # 0.1% per trade
    slippage_pct: float = 0.0005  # 0.05% slippage
    position_size_pct: float = 1.0  # 100% of capital per trade
    min_trade_interval: int = 1  # Minimum bars between trades
    max_positions: int = 1  # Only 1 position at a time for now


@dataclass
class Trade:
    """Record of a single trade."""

    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_price: float
    exit_price: float
    size: float
    side: str  # 'long' or 'short'
    pnl: float
    pnl_pct: float
    commission: float


@dataclass
class BacktestResult:
    """Results of a backtest."""

    trades: list[Trade]
    equity_curve: pd.Series
    positions: pd.Series
    returns: pd.Series
    config: BacktestConfig
    metadata: dict[str, Any]


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
        """Generate trades from signals.

        Args:
            data: OHLCV data
            signals: Trading signals (1=long, -1=short, 0=neutral)
            position_sizes: Position sizes per trade

        Returns:
            List of Trade objects
        """
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
                        pnl_pct=(
                            pnl
                            / (
                                current_position["size"]
                                * current_position["entry_price"]
                            )
                            * 100
                        ),
                        commission=current_position["entry_commission"]
                        + commission,
                    )
                    trades.append(trade)

                    current_position = None
                    last_trade_idx = i

            # Enter new position if signal is non-zero and we're flat
            if current_position is None and signal != 0:
                # Check max positions
                if self.config.max_positions == 1 or len(trades) == 0:
                    # Entry at current price with slippage
                    entry_price = self._apply_slippage(
                        prices[i], signal, is_entry=True
                    )

                    # Calculate position size
                    capital = self.config.initial_capital
                    if len(trades) > 0:
                        # Update capital based on previous trades
                        capital += sum(t.pnl for t in trades)

                    position_value = capital * position_sizes.iloc[i]
                    size = position_value / entry_price

                    # Entry commission
                    entry_commission = (
                        abs(size * entry_price) * self.config.commission_pct
                    )

                    current_position = {
                        "entry_time": time,
                        "entry_price": entry_price,
                        "size": size,
                        "side": int(signal),
                        "entry_commission": entry_commission,
                    }
                    last_trade_idx = i

        # Close any open position at the end
        if current_position is not None:
            exit_price = self._apply_slippage(
                prices[-1], current_position["side"], is_entry=False
            )

            if current_position["side"] == 1:
                pnl = current_position["size"] * (
                    exit_price - current_position["entry_price"]
                )
            else:
                pnl = current_position["size"] * (
                    current_position["entry_price"] - exit_price
                )

            commission = (
                abs(current_position["size"] * exit_price)
                * self.config.commission_pct
            )
            pnl -= commission

            trade = Trade(
                entry_time=current_position["entry_time"],
                exit_time=times[-1],
                entry_price=current_position["entry_price"],
                exit_price=exit_price,
                size=current_position["size"],
                side="long" if current_position["side"] == 1 else "short",
                pnl=pnl,
                pnl_pct=(
                    pnl
                    / (current_position["size"] * current_position["entry_price"])
                    * 100
                ),
                commission=current_position["entry_commission"] + commission,
            )
            trades.append(trade)

        return trades

    def _apply_slippage(
        self, price: float, side: int, is_entry: bool
    ) -> float:
        """Apply slippage to price.

        Args:
            price: Market price
            side: 1 for long, -1 for short
            is_entry: True for entry, False for exit

        Returns:
            Price with slippage applied
        """
        # For long entry or short exit: pay more (worse price)
        # For short entry or long exit: receive less (worse price)
        if (side == 1 and is_entry) or (side == -1 and not is_entry):
            return price * (1 + self.config.slippage_pct)
        else:
            return price * (1 - self.config.slippage_pct)

    def _calculate_equity_curve(
        self, data: pd.DataFrame, trades: list[Trade]
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate equity curve from trades.

        Args:
            data: OHLCV data
            trades: List of trades

        Returns:
            Tuple of (equity_curve, positions, returns)
        """
        # Initialize equity curve
        equity = pd.Series(
            self.config.initial_capital, index=data.index, dtype=float
        )
        positions = pd.Series(0, index=data.index, dtype=int)

        # Apply trades to equity curve
        cumulative_pnl = 0.0
        for trade in trades:
            cumulative_pnl += trade.pnl

            # Update equity for all times after trade exit
            mask = data.index > trade.exit_time
            equity.loc[mask] = self.config.initial_capital + cumulative_pnl

            # Mark position periods
            position_mask = (data.index >= trade.entry_time) & (
                data.index <= trade.exit_time
            )
            positions.loc[position_mask] = 1 if trade.side == "long" else -1

        # Calculate returns
        returns = equity.pct_change().fillna(0)

        return equity, positions, returns
