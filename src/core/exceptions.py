"""Base exception hierarchy for AITrader.

All divisions raise subclasses of AITraderError.
Catch AITraderError at the top level (D11) to surface to OPS.
"""

from __future__ import annotations


class AITraderError(Exception):
    """Root exception for the AITrader system."""


# ── Data layer (D02) ──────────────────────────────────────────────────────────

class DataError(AITraderError):
    """Raised by D02-DATA on fetch failures, schema violations, or store errors.

    Never return empty data silently — always raise DataError so D11 can surface it.
    """


# ── Signal layer (D03, D04, D05) ─────────────────────────────────────────────

class SignalError(AITraderError):
    """Raised when a division fails to produce a valid signal."""


# ── Execution layer (D06) ─────────────────────────────────────────────────────

class ExecutionError(AITraderError):
    """Raised by D06-EXECUTION on order rejection or broker communication errors."""


class RiskViolation(ExecutionError):
    """Raised when the risk manager hard-stops a proposed order.

    Examples: daily drawdown exceeded, position size too large, news halt active.
    """


# ── Bus layer (D01) ───────────────────────────────────────────────────────────

class BusError(AITraderError):
    """Raised on bus publish/subscribe failures (queue full, serialization errors, etc.)."""


# ── Config layer ──────────────────────────────────────────────────────────────

class ConfigError(AITraderError):
    """Raised on missing or invalid configuration values."""


# ── Backtest / Replay layer (D08) ─────────────────────────────────────────────

class ReplayError(AITraderError):
    """Raised on replay control errors (invalid time travel, clock not in replay mode, etc.)."""
