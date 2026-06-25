"""D02-DATA — purge corrupted flat bars and re-fetch from Dukascopy."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.core.contracts import Instrument, Timeframe
from src.core.logging import get_logger
from src.data.feeds.dukascopy import DukascopyFeed
from src.data.pipeline.backfill import backfill_instrument
from src.data.pipeline.merge import is_flat_bar
from src.data.store import DataStore

_log = get_logger("D02-DATA")

_HIGHER_TIMEFRAMES = [
    Timeframe.M5,
    Timeframe.M15,
    Timeframe.M30,
    Timeframe.H1,
    Timeframe.H4,
    Timeframe.D1,
]


def _is_corrupt_bar(row: pd.Series) -> bool:
    """Yahoo-style garbage: zero spread and zero volume."""
    return is_flat_bar(row) and float(row.get("volume", 0) or 0) <= 0


def purge_corrupt_rows(
    store: DataStore,
    instrument: Instrument,
    timeframe: Timeframe,
    start: datetime,
    end: datetime,
) -> int:
    """Remove flat zero-volume rows from monthly partitions. Returns rows removed."""
    start = start.astimezone(timezone.utc)
    end = end.astimezone(timezone.utc)
    root = store.base_dir / "raw" / instrument.value / timeframe.value
    if not root.exists():
        return 0

    removed = 0
    for path in sorted(root.glob("*.parquet")):
        df = pd.read_parquet(path)
        df.index = pd.to_datetime(df.index, utc=True)
        in_range = df.loc[start:end]
        if in_range.empty:
            continue

        corrupt_mask = df.index.isin(in_range.index) & df.apply(_is_corrupt_bar, axis=1)
        if not corrupt_mask.any():
            continue

        cleaned = df.loc[~corrupt_mask]
        removed += int(corrupt_mask.sum())
        tmp = path.with_suffix(".parquet.tmp")
        cleaned.to_parquet(tmp)
        tmp.rename(path)
        _log.info(
            "repair_partition_purged",
            path=str(path),
            removed=int(corrupt_mask.sum()),
            remaining=len(cleaned),
        )

    return removed


def trim_higher_tf_beyond_m1(store: DataStore, instrument: Instrument) -> int:
    """Drop higher-TF rows that extend past the last stored 1m bar (orphan tail)."""
    _, last_m1 = store.list_ohlcv_range(instrument, Timeframe.M1)
    if last_m1 is None:
        return 0

    last_m1 = last_m1.astimezone(timezone.utc)
    trimmed = 0
    for tf in _HIGHER_TIMEFRAMES:
        root = store.base_dir / "raw" / instrument.value / tf.value
        if not root.exists():
            continue
        for path in sorted(root.glob("*.parquet")):
            df = pd.read_parquet(path)
            df.index = pd.to_datetime(df.index, utc=True)
            orphans = df.index > last_m1
            if not orphans.any():
                continue
            kept = df.loc[~orphans]
            trimmed += int(orphans.sum())
            tmp = path.with_suffix(".parquet.tmp")
            kept.to_parquet(tmp)
            tmp.rename(path)
            _log.info(
                "repair_trimmed_orphan_tf",
                timeframe=tf.value,
                path=str(path),
                removed=int(orphans.sum()),
                last_m1=last_m1.isoformat(),
            )
    return trimmed


def repair_instrument(
    store: DataStore,
    feed: DukascopyFeed,
    instrument: Instrument,
    start: datetime,
    end: datetime | None = None,
) -> dict[str, int]:
    """Purge corrupt bars then re-download M1 and resample affected months."""
    end = end or datetime.now(timezone.utc)
    start = start.astimezone(timezone.utc)
    end = end.astimezone(timezone.utc)

    removed = purge_corrupt_rows(store, instrument, Timeframe.M1, start, end)
    for tf in _HIGHER_TIMEFRAMES:
        removed += purge_corrupt_rows(store, instrument, tf, start, end)

    rows = backfill_instrument(store, feed, instrument, start, end, resample_higher=True)
    trimmed = trim_higher_tf_beyond_m1(store, instrument)

    _log.info(
        "repair_complete",
        instrument=instrument.value,
        removed=removed,
        refetched_m1=rows,
        trimmed_orphans=trimmed,
    )
    return {"removed": removed, "refetched_m1": rows, "trimmed_orphans": trimmed}