"""Scheduler shared types and constants."""

from __future__ import annotations

from typing import TypedDict

from src.core.contracts import Timeframe

FOCUSED_POLL_INTERVAL_SEC = 2.0
BACKGROUND_POLL_INTERVAL_SEC = 10.0

INTRADAY_FOCUS_TFS: frozenset[Timeframe] = frozenset(
    {Timeframe.M1, Timeframe.M5, Timeframe.M15, Timeframe.M30}
)

# Light focus polls can hydrate from Parquet (chart already reads the store).
STORE_ONLY_LIGHT_TFS: frozenset[Timeframe] = frozenset(
    {Timeframe.H1, Timeframe.H4, Timeframe.D1, Timeframe.W1}
)

# Intraday live polls need a Dukascopy M1 window (short lookback on focus change).
M1_LIVE_DERIVED_TFS: frozenset[Timeframe] = frozenset(
    {Timeframe.M1, Timeframe.M5, Timeframe.M15, Timeframe.M30}
)

LIGHT_M1_LOOKBACK_HOURS = 8.0


class PairLiveStatus(TypedDict, total=False):
    last_bar_at: str
    close: float
    source: str
    last_error: str
    last_poll_at: str