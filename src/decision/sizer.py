"""D05-DECISION — Position sizing logic.

Calculates suggested position size in lots based on account equity, risk limits,
and stop loss distance.
"""

from __future__ import annotations

from src.core.config import InstrumentConfig
from src.core.contracts import PortfolioState


def compute_suggested_size(
    entry_price: float | None,
    sl_price: float | None,
    inst_config: InstrumentConfig,
    portfolio_state: PortfolioState | None,
    default_equity: float = 100000.0,
    risk_pct: float = 0.01,
) -> float:
    """Compute position size in lots based on fixed fractional risk.

    Formula:
        risk_amount = equity * risk_pct
        pip_value = pip_size * lot_size
        size_lots = risk_amount / (stop_loss_distance / pip_value)
    """
    equity = portfolio_state.equity if portfolio_state else default_equity

    # Fallback to safe default lot size if entry or SL are missing
    if entry_price is None or sl_price is None:
        return min(0.1, inst_config.max_position_lots)

    stop_distance = abs(entry_price - sl_price)
    if stop_distance <= 0.0:
        return min(0.1, inst_config.max_position_lots)

    risk_amount = equity * risk_pct
    risk_per_lot = stop_distance * inst_config.lot_size

    if risk_per_lot <= 0.0:
        return min(0.1, inst_config.max_position_lots)

    # Lots calculation
    size_lots = risk_amount / risk_per_lot

    # Ensure within max bounds and format to 2 decimal places
    size_lots = min(size_lots, inst_config.max_position_lots)
    return round(max(0.01, size_lots), 2)
