"""Gap-fill decision helpers — import-safe (no Dukascopy feed dependency)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from src.core.contracts import Instrument, Timeframe

_TF_STEP = {
    Timeframe.M1: timedelta(minutes=1),
    Timeframe.M5: timedelta(minutes=5),
    Timeframe.M15: timedelta(minutes=15),
    Timeframe.M30: timedelta(minutes=30),
    Timeframe.H1: timedelta(hours=1),
    Timeframe.H4: timedelta(hours=4),
    Timeframe.D1: timedelta(days=1),
    Timeframe.W1: timedelta(weeks=1),
}


def store_needs_gap_fill(
    data_store: Any,
    instrument: Instrument,
    timeframe: Timeframe,
    end_dt: datetime,
    *,
    auto_refresh: bool,
) -> bool:
    """Return True when the chart request needs a Dukascopy tail fill for this pair."""
    if not auto_refresh:
        return True

    _, last_ts = data_store.list_ohlcv_range(instrument, timeframe)
    if last_ts is None:
        return True

    end_dt = min(end_dt.astimezone(timezone.utc), datetime.now(timezone.utc))
    last_ts = last_ts.astimezone(timezone.utc)
    step = _TF_STEP.get(timeframe, timedelta(hours=1))
    # Stale when store ends more than ~2 bars before the requested window end.
    return last_ts + step * 2 < end_dt