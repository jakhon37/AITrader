"""Parquet read/write helpers for the scheduler."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from src.core.candle import TF_DURATION, candle_open_time, tf_duration
from src.core.contracts import Instrument, OHLCVBar, Timeframe
from src.core.exceptions import DataError
from src.core.ids import new_signal_id
from src.core.logging import get_logger
from src.data.scheduler.bars import normalize_wick
from src.data.store import DataStore

_log = get_logger("D02-DATA")

_M1_SYNC_LOOKBACK = timedelta(hours=8)


def sync_m1_window_to_store(
    store: DataStore,
    instrument: Instrument,
    m1_df: pd.DataFrame,
    now: datetime,
    *,
    lookback: timedelta = _M1_SYNC_LOOKBACK,
) -> int:
    """Persist completed M1 rows from a live fetch window (fills intraday holes)."""
    if m1_df.empty:
        return 0

    now = now.astimezone(timezone.utc)
    active_open = candle_open_time(now, Timeframe.M1)
    df = m1_df.sort_index()
    completed = df.loc[df.index < active_open]
    if completed.empty:
        return 0

    _, last_ts = store.list_ohlcv_range(instrument, Timeframe.M1)
    window_start = now - lookback
    if last_ts is not None:
        last_ts = last_ts.astimezone(timezone.utc)
        window_start = max(window_start, last_ts + timedelta(minutes=1))

    to_write = completed.loc[completed.index >= window_start]
    if to_write.empty:
        return 0

    try:
        store.write_ohlcv(instrument, Timeframe.M1, to_write)
        _log.debug(
            "scheduler_m1_window_synced",
            instrument=instrument.value,
            rows=len(to_write),
            from_ts=str(to_write.index[0]),
            to_ts=str(to_write.index[-1]),
        )
        return len(to_write)
    except Exception as exc:
        _log.error(
            "scheduler_m1_window_sync_failed",
            instrument=instrument.value,
            error=str(exc),
        )
        return 0


def save_bar_to_store(
    store: DataStore,
    instrument: Instrument,
    timeframe: Timeframe,
    bar: OHLCVBar,
) -> None:
    """Store bar in DataStore without downgrading existing wicks."""
    try:
        bar = normalize_wick(bar)
        dur = tf_duration(timeframe)
        try:
            existing = store.get_ohlcv(
                instrument,
                timeframe,
                bar.timestamp,
                bar.timestamp + dur - timedelta(microseconds=1),
            )
        except DataError:
            existing = pd.DataFrame()

        if not existing.empty:
            row = existing.iloc[-1]
            old_spread = float(row["high"]) - float(row["low"])
            new_spread = bar.high - bar.low
            if new_spread <= 0 and old_spread > 0:
                return
            if old_spread > 0 or new_spread > 0:
                bar = bar.model_copy(
                    update={
                        "open": float(row["open"]),
                        "high": max(bar.high, float(row["high"])),
                        "low": min(bar.low, float(row["low"])),
                        "close": bar.close,
                        "volume": max(bar.volume, float(row.get("volume", 0.0) or 0.0)),
                    }
                )
                bar = normalize_wick(bar)

        row_df = pd.DataFrame(
            {
                "open": [bar.open],
                "high": [bar.high],
                "low": [bar.low],
                "close": [bar.close],
                "volume": [bar.volume],
            },
            index=pd.DatetimeIndex([bar.timestamp], tz="UTC"),
        )
        store.write_ohlcv(instrument, timeframe, row_df)
    except Exception as exc:
        _log.error(
            "scheduler_store_failed",
            instrument=instrument.value,
            timeframe=timeframe.value,
            error=str(exc),
        )


def bars_from_store(
    store: DataStore,
    instrument: Instrument,
    timeframe: Timeframe,
) -> tuple[OHLCVBar, OHLCVBar | None]:
    """Read the latest completed/active bars from Parquet when Dukascopy is busy."""
    now = datetime.now(timezone.utc)
    dur = TF_DURATION[timeframe]
    candle_open = candle_open_time(now, timeframe)
    df = store.get_ohlcv(
        instrument,
        timeframe,
        candle_open - dur * 5,
        now,
    )
    if df.empty:
        raise DataError(f"No stored bars for {instrument.value}/{timeframe.value}")

    def _row_to_bar(ts: datetime, row: pd.Series, source: str) -> OHLCVBar:
        return OHLCVBar(
            signal_id=new_signal_id(),
            instrument=instrument,
            timeframe=timeframe,
            timestamp=ts,
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row.get("volume", 0.0) or 0.0),
            source=source,
        )

    active_bar: OHLCVBar | None = None
    completed_bar: OHLCVBar | None = None
    if candle_open in df.index:
        active_bar = _row_to_bar(candle_open, df.loc[candle_open], "store_active")
        prior = df.loc[: candle_open - timedelta(microseconds=1)]
        if not prior.empty:
            ts = prior.index[-1].to_pydatetime()
            completed_bar = _row_to_bar(ts, prior.iloc[-1], "store")
    else:
        ts = df.index[-1].to_pydatetime()
        completed_bar = _row_to_bar(ts, df.iloc[-1], "store")

    if completed_bar is None:
        raise DataError(f"No completed bar in store for {instrument.value}/{timeframe.value}")
    return normalize_wick(completed_bar), (
        normalize_wick(active_bar) if active_bar is not None else None
    )


def load_bar_from_store(
    store: DataStore,
    instrument: Instrument,
    timeframe: Timeframe,
    candle_open: datetime,
) -> OHLCVBar:
    """Read a single bar from the DataStore by its open timestamp (replay)."""
    dur = tf_duration(timeframe)
    df = store.get_ohlcv(
        instrument,
        timeframe,
        start=candle_open,
        end=candle_open + dur - timedelta(seconds=1),
    )
    if df.empty:
        raise DataError(
            f"No bar at {candle_open} for {instrument.value}/{timeframe.value}"
        )
    row = df.iloc[0]
    return OHLCVBar(
        signal_id=new_signal_id(),
        instrument=instrument,
        timeframe=timeframe,
        timestamp=df.index[0].to_pydatetime(),
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=float(row.get("volume", 0.0) or 0.0),
        source="replay",
    )