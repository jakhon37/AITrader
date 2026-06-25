"""D02-DATA — full historical backfill via Dukascopy."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from src.core.contracts import Instrument, Timeframe
from src.core.logging import get_logger
from src.data.feeds.dukascopy import DukascopyFeed
from src.data.pipeline.resample import resample_higher_timeframes
from src.data.store import DataStore

_log = get_logger("D02-DATA")

_DEFAULT_TIMEFRAMES = [Timeframe.M1]


def backfill_instrument(
    store: DataStore,
    feed: DukascopyFeed,
    instrument: Instrument,
    start: datetime,
    end: datetime,
    *,
    timeframes: list[Timeframe] | None = None,
    resample_higher: bool = True,
    resample_targets: list[Timeframe] | None = None,
) -> int:
    """Download M1 history and optionally resample to higher TFs. Returns M1 rows."""
    start = start.astimezone(timezone.utc)
    end = end.astimezone(timezone.utc)
    tfs = timeframes or _DEFAULT_TIMEFRAMES

    total = 0
    if Timeframe.M1 in tfs:
        df = feed.fetch_range(instrument, Timeframe.M1, start, end)
        if not df.empty:
            store.write_ohlcv(instrument, Timeframe.M1, df)
            total = len(df)
            _log.info("backfill_m1_complete", instrument=instrument.value, rows=total)

    if resample_higher and total > 0:
        affected_months = sorted({ts.strftime("%Y-%m") for ts in df.index})
        resample_higher_timeframes(
            store,
            instrument,
            months=affected_months,
            force=True,
            targets=resample_targets,
        )

    return total