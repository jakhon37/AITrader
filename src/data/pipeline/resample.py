"""D02-DATA — resample stored 1m partitions to higher timeframes."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.core.contracts import Instrument, Timeframe
from src.core.logging import get_logger
from src.data.store import DataStore

_log = get_logger("D02-DATA")

_TARGET_RULES: list[tuple[Timeframe, str]] = [
    (Timeframe.M5, "5min"),
    (Timeframe.M15, "15min"),
    (Timeframe.M30, "30min"),
    (Timeframe.H1, "1h"),
    (Timeframe.H4, "4h"),
    (Timeframe.D1, "1d"),
]


def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    resampler = df.resample(rule, closed="left", label="left")
    out = pd.DataFrame()
    out["open"] = resampler["open"].first()
    out["high"] = resampler["high"].max()
    out["low"] = resampler["low"].min()
    out["close"] = resampler["close"].last()
    out["volume"] = resampler["volume"].sum()
    return out.dropna()


_FAST_RESAMPLE_TFS = {
    Timeframe.M5,
    Timeframe.M15,
    Timeframe.M30,
    Timeframe.H1,
}
_SLOW_RESAMPLE_TFS = {Timeframe.H4, Timeframe.D1}


def resample_higher_timeframes(
    store: DataStore,
    instrument: Instrument,
    *,
    months: list[str] | None = None,
    force: bool = False,
    targets: list[Timeframe] | None = None,
) -> int:
    """Resample 1m parquet partitions for an instrument. Returns rows written."""
    source_dir = store.base_dir / "raw" / instrument.value / Timeframe.M1.value
    if not source_dir.exists():
        _log.warning("resample_no_1m_dir", instrument=instrument.value, path=str(source_dir))
        return 0

    files = sorted(source_dir.glob("*.parquet"))
    if months is not None:
        month_set = set(months)
        files = [f for f in files if f.stem in month_set]
    total = 0
    for path in files:
        df = pd.read_parquet(path)
        df.index = pd.to_datetime(df.index, utc=True)
        rules = _TARGET_RULES
        if targets is not None:
            target_set = set(targets)
            rules = [(tf, rule) for tf, rule in _TARGET_RULES if tf in target_set]
        for tf, rule in rules:
            target_dir = store.base_dir / "raw" / instrument.value / tf.value
            target_path = target_dir / path.name
            if target_path.exists() and not force:
                continue
            resampled = resample_ohlcv(df, rule)
            if resampled.empty:
                continue
            store.write_ohlcv(instrument, tf, resampled)
            total += len(resampled)
    return total