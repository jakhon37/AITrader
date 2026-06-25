"""D02-DATA — tail refresh orchestration (daily/weekly modes)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.core.config import AppConfig, load_config
from src.core.contracts import Instrument, Timeframe
from src.core.instruments import get_enabled_instruments
from src.core.logging import get_logger
from src.data.feeds.dukascopy import DukascopyFeed
from src.data.pipeline.backfill import backfill_instrument
from src.data.pipeline.resample import (
    _FAST_RESAMPLE_TFS,
    _SLOW_RESAMPLE_TFS,
    resample_higher_timeframes,
)
from src.data.store import DataStore

_log = get_logger("D02-DATA")


def _enabled_instruments(cfg: AppConfig) -> list[Instrument]:
    return get_enabled_instruments(cfg)


def _recent_months(store: DataStore, instrument: Instrument, tail_days: int) -> list[str]:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=tail_days)
    _, last_m1 = store.list_ohlcv_range(instrument, Timeframe.M1)
    if last_m1 is not None:
        start = min(start, last_m1 - timedelta(days=1))
    months: set[str] = set()
    cursor = datetime(start.year, start.month, 1, tzinfo=timezone.utc)
    while cursor <= now:
        months.add(cursor.strftime("%Y-%m"))
        if cursor.month == 12:
            cursor = datetime(cursor.year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            cursor = datetime(cursor.year, cursor.month + 1, 1, tzinfo=timezone.utc)
    return sorted(months)


def refresh_instrument(
    store: DataStore,
    feed: DukascopyFeed,
    instrument: Instrument,
    *,
    mode: str = "tail",
    tail_days: int = 14,
    full_lookback_days: int = 365 * 5,
    resample_targets: list[Timeframe] | None = None,
    fetch_m1: bool = True,
) -> int:
    """Refresh one instrument. mode='tail' fetches recent days; mode='full' does deep backfill."""
    now = datetime.now(timezone.utc)
    if mode == "full":
        start = now - timedelta(days=full_lookback_days)
    else:
        start = now - timedelta(days=tail_days)
        _, last_m1 = store.list_ohlcv_range(instrument, Timeframe.M1)
        if last_m1 is not None:
            start = min(start, last_m1 - timedelta(days=1))

    rows = 0
    if fetch_m1:
        targets = (
            list(_FAST_RESAMPLE_TFS)
            if resample_targets is None
            else resample_targets
        )
        rows = backfill_instrument(
            store,
            feed,
            instrument,
            start,
            now,
            resample_higher=bool(targets),
            resample_targets=targets,
        )
    elif resample_targets:
        months = _recent_months(store, instrument, tail_days)
        rows = resample_higher_timeframes(
            store,
            instrument,
            months=months,
            force=True,
            targets=resample_targets,
        )
    _log.info("refresh_complete", instrument=instrument.value, mode=mode, rows=rows)
    return rows


def refresh_all_enabled(
    store: DataStore,
    feed: DukascopyFeed,
    cfg: AppConfig | None = None,
    *,
    mode: str = "tail",
    resample_targets: list[Timeframe] | None = None,
    fetch_m1: bool = True,
) -> dict[str, int]:
    """Refresh every enabled instrument from config."""
    cfg = cfg or load_config()
    tail_days = cfg.data.pipeline.tail_days
    full_days = cfg.data.pipeline.full_lookback_days
    results: dict[str, int] = {}
    for inst in _enabled_instruments(cfg):
        results[inst.value] = refresh_instrument(
            store,
            feed,
            inst,
            mode=mode,
            tail_days=tail_days,
            full_lookback_days=full_days,
            resample_targets=resample_targets,
            fetch_m1=fetch_m1,
        )
    return results


def refresh_slow_resample_all(
    store: DataStore,
    cfg: AppConfig | None = None,
) -> dict[str, int]:
    """Resample 4h/1d from stored M1 without a new Dukascopy fetch."""
    return refresh_all_enabled(
        store,
        DukascopyFeed(),
        cfg,
        resample_targets=list(_SLOW_RESAMPLE_TFS),
        fetch_m1=False,
    )