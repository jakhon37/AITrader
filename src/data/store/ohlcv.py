"""D02-DATA — OHLCV storage and retrieval mixin using Parquet."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from src.core.contracts import Instrument, Timeframe
from src.core.exceptions import DataError
from src.core.logging import get_logger
from src.data.pipeline.merge import merge_ohlcv_without_downgrade

_log = get_logger("D02-DATA")


def _parquet_path(base_dir: Path, instrument: Instrument, timeframe: Timeframe, dt: datetime) -> Path:
    """Return the monthly Parquet file path for a given instrument/timeframe/month."""
    month_key = dt.strftime("%Y-%m")
    return base_dir / "raw" / instrument.value / timeframe.value / f"{month_key}.parquet"


def _ensure_utc(ts: pd.Series) -> pd.Series:  # noqa: UP007
    """Ensure a datetime Series is UTC-aware; raise DataError if tz-naive."""
    if ts.dt.tz is None:
        raise DataError(
            "Timestamps must be timezone-aware UTC. "
            "Localize with df.index = df.index.tz_localize('UTC') before storing."
        )
    return ts.dt.tz_convert("UTC")


class OHLCVMixin:
    """Mixin for Parquet-based OHLCV storage.

    Expects self._base (Path) to be populated by the base class.
    """

    def write_ohlcv(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
        df: pd.DataFrame,
    ) -> None:
        """Append validated OHLCV rows to the monthly Parquet partition.

        Parameters
        ----------
        instrument:
            The instrument enum (e.g. Instrument.EURUSD).
        timeframe:
            The timeframe enum (e.g. Timeframe.H1).
        df:
            DataFrame with a timezone-aware UTC DatetimeIndex and columns:
            open, high, low, close, volume (volume may be 0 for Forex).

        Raises
        ------
        DataError
            If the DataFrame is empty, has tz-naive index, or is missing columns.
        """
        if df.empty:
            raise DataError(f"write_ohlcv: empty DataFrame for {instrument.value}/{timeframe.value}")

        if not isinstance(df.index, pd.DatetimeIndex):
            raise DataError("write_ohlcv: DataFrame index must be a DatetimeIndex.")

        if df.index.tz is None:
            raise DataError(
                "write_ohlcv: DatetimeIndex must be timezone-aware (UTC). "
                "Use df.index = df.index.tz_localize('UTC')."
            )

        required = {"open", "high", "low", "close"}
        missing = required - set(df.columns)
        if missing:
            raise DataError(f"write_ohlcv: missing columns {sorted(missing)}")

        # Group by month and write/append per partition
        df = df.copy()
        df.index = df.index.tz_convert("UTC")

        # Add volume column if absent (0.0 for Forex pairs that don't report volume)
        if "volume" not in df.columns:
            df["volume"] = 0.0

        df["_partition_month"] = df.index.strftime("%Y-%m")
        for _month_key, chunk in df.groupby("_partition_month"):
            chunk = chunk.drop(columns=["_partition_month"])
            # Use the first timestamp of the chunk to build the path
            sample_dt = chunk.index[0].to_pydatetime()
            path = _parquet_path(self._base, instrument, timeframe, sample_dt)
            path.parent.mkdir(parents=True, exist_ok=True)

            tmp_path = path.with_suffix(".parquet.tmp")
            try:
                if path.exists():
                    existing = pd.read_parquet(path)
                    existing.index = pd.to_datetime(existing.index, utc=True)
                    combined = merge_ohlcv_without_downgrade(
                        existing,
                        chunk[["open", "high", "low", "close", "volume"]],
                    )
                    combined.to_parquet(tmp_path)
                else:
                    chunk[["open", "high", "low", "close", "volume"]].to_parquet(tmp_path)
                
                # Atomic rename on the same filesystem
                tmp_path.rename(path)
            except Exception as e:
                if tmp_path.exists():
                    try:
                        tmp_path.unlink()
                    except Exception:
                        pass
                raise e

            _log.debug(
                "ohlcv_written",
                instrument=instrument.value,
                timeframe=timeframe.value,
                rows=len(chunk),
                path=str(path),
            )

    def get_ohlcv(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """Query OHLCV bars in the [start, end] range (inclusive).

        Parameters
        ----------
        instrument, timeframe:
            Which partition to read.
        start, end:
            UTC-aware datetimes. Both are required.

        Returns
        -------
        pd.DataFrame
            Indexed by UTC datetime, columns: open, high, low, close, volume.
            Sorted ascending by timestamp.

        Raises
        ------
        DataError
            If start/end are tz-naive, or if no Parquet files exist for the
            requested range.
        """
        if start.tzinfo is None or end.tzinfo is None:
            raise DataError("get_ohlcv: start and end must be timezone-aware UTC datetimes.")
        if start > end:
            raise DataError(f"get_ohlcv: start ({start}) is after end ({end}).")

        start = start.astimezone(timezone.utc)
        end = end.astimezone(timezone.utc)

        # Collect all monthly Parquet files that overlap the requested range
        parquet_root = self._base / "raw" / instrument.value / timeframe.value
        if not parquet_root.exists():
            raise DataError(
                f"No data for {instrument.value}/{timeframe.value}. "
                f"Expected directory: {parquet_root}. "
                "Run download_sample_data.py or write OHLCV first."
            )

        files = sorted(parquet_root.glob("*.parquet"))
        if not files:
            raise DataError(
                f"No Parquet files found in {parquet_root} for "
                f"{instrument.value}/{timeframe.value}."
            )

        # Filter to months that overlap [start, end]
        relevant: list[Path] = []
        for f in files:
            stem = f.stem  # "YYYY-MM"
            try:
                file_period = pd.Period(stem, freq="M")
            except Exception:
                continue
            file_start = file_period.start_time.tz_localize("UTC")
            file_end = file_period.end_time.tz_localize("UTC")
            if file_start <= end and file_end >= start:
                relevant.append(f)

        if not relevant:
            raise DataError(
                f"No OHLCV data found for {instrument.value}/{timeframe.value} "
                f"between {start.date()} and {end.date()}."
            )

        chunks = []
        for f in relevant:
            try:
                chunk = pd.read_parquet(f)
                chunk.index = pd.to_datetime(chunk.index, utc=True)
                chunks.append(chunk)
            except Exception as exc:
                raise DataError(f"Failed to read Parquet {f}: {exc}") from exc

        df = pd.concat(chunks)
        df = df[~df.index.duplicated(keep="last")]
        df.sort_index(inplace=True)

        # Slice to requested range
        df = df.loc[start:end]

        if df.empty:
            raise DataError(
                f"OHLCV query returned empty result for {instrument.value}/{timeframe.value} "
                f"[{start.date()} → {end.date()}]. Data exists but not in this range."
            )

        _log.debug(
            "ohlcv_queried",
            instrument=instrument.value,
            timeframe=timeframe.value,
            rows=len(df),
            start=str(start.date()),
            end=str(end.date()),
        )
        return df

    def peek_latest_ohlcv(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
    ) -> tuple[Optional[datetime], Optional[float]]:
        """Read only the latest partition tail — O(1) file read for status probes."""
        parquet_root = self._base / "raw" / instrument.value / timeframe.value
        if not parquet_root.exists():
            return None, None
        files = sorted(parquet_root.glob("*.parquet"))
        if not files:
            return None, None
        try:
            chunk = pd.read_parquet(files[-1])
            chunk.index = pd.to_datetime(chunk.index, utc=True)
            if chunk.empty:
                return None, None
            last_ts = chunk.index[-1].to_pydatetime()
            return last_ts, float(chunk.iloc[-1]["close"])
        except Exception:
            return None, None

    def list_ohlcv_range(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
    ) -> tuple[Optional[datetime], Optional[datetime]]:
        """Return the (earliest, latest) timestamps available, or (None, None) if no data."""
        parquet_root = self._base / "raw" / instrument.value / timeframe.value
        if not parquet_root.exists():
            return None, None
        files = sorted(parquet_root.glob("*.parquet"))
        if not files:
            return None, None

        first_ts: Optional[datetime] = None
        last_ts: Optional[datetime] = None
        try:
            first_chunk = pd.read_parquet(files[0])
            first_chunk.index = pd.to_datetime(first_chunk.index, utc=True)
            if not first_chunk.empty:
                first_ts = first_chunk.index[0].to_pydatetime()
        except Exception:
            pass
        try:
            last_chunk = pd.read_parquet(files[-1])
            last_chunk.index = pd.to_datetime(last_chunk.index, utc=True)
            if not last_chunk.empty:
                last_ts = last_chunk.index[-1].to_pydatetime()
        except Exception:
            pass
        return first_ts, last_ts
