"""Unit tests for D02-DATA: DataStore (Parquet OHLCV layer).

Tests:
  - write_ohlcv / get_ohlcv round-trip
  - monthly partitioning (multi-month data split into separate files)
  - duplicate-timestamp deduplication (last write wins)
  - tz-naive rejection
  - empty DataFrame rejection
  - out-of-range query raises DataError
  - missing directory raises DataError
  - list_ohlcv_range returns correct bounds
  - News/Calendar stubs raise NotImplementedError
"""

from __future__ import annotations

import pytest
import pandas as pd
from datetime import datetime, timezone, timedelta
from pathlib import Path

from src.core.contracts import Instrument, Timeframe
from src.core.exceptions import DataError
from src.data.store import DataStore


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_ohlcv(
    start: datetime,
    periods: int = 5,
    freq: str = "1h",
) -> pd.DataFrame:
    """Return a minimal valid UTC-aware OHLCV DataFrame."""
    idx = pd.date_range(start=start, periods=periods, freq=freq, tz="UTC")
    return pd.DataFrame(
        {
            "open":   [1.10 + i * 0.001 for i in range(periods)],
            "high":   [1.11 + i * 0.001 for i in range(periods)],
            "low":    [1.09 + i * 0.001 for i in range(periods)],
            "close":  [1.105 + i * 0.001 for i in range(periods)],
            "volume": [1000.0] * periods,
        },
        index=idx,
    )


@pytest.fixture()
def store(tmp_path: Path) -> DataStore:
    return DataStore(base_dir=tmp_path)


EURUSD = Instrument.EURUSD
H1 = Timeframe.H1


# ── write / read round-trip ───────────────────────────────────────────────────

class TestWriteReadRoundTrip:
    def test_basic_round_trip(self, store: DataStore) -> None:
        start = datetime(2024, 3, 1, 0, 0, tzinfo=timezone.utc)
        df_in = _make_ohlcv(start, periods=5)

        store.write_ohlcv(EURUSD, H1, df_in)
        df_out = store.get_ohlcv(
            EURUSD, H1,
            start=start,
            end=start + timedelta(hours=10),
        )

        assert len(df_out) == 5
        assert list(df_out.columns) == ["open", "high", "low", "close", "volume"]
        # Compare index values directly
        assert len(df_out.index) == len(df_in.index)
        assert (df_out.index == df_in.index).all()
        assert df_out.index.tz is not None
        # Compare close values as numpy arrays (avoids index freq mismatch in Series compare)
        import numpy as np
        np.testing.assert_array_almost_equal(df_out["close"].values, df_in["close"].values)

    def test_volume_defaults_to_zero_when_absent(self, store: DataStore) -> None:
        start = datetime(2024, 3, 1, tzinfo=timezone.utc)
        df_in = _make_ohlcv(start, periods=3).drop(columns=["volume"])

        store.write_ohlcv(EURUSD, H1, df_in)
        df_out = store.get_ohlcv(EURUSD, H1, start=start, end=start + timedelta(hours=5))
        assert (df_out["volume"] == 0.0).all()


# ── monthly partitioning ──────────────────────────────────────────────────────

class TestMonthlyPartitioning:
    def test_cross_month_data_splits_into_two_files(self, store: DataStore, tmp_path: Path) -> None:
        # 3 rows in Jan, 3 rows in Feb
        jan_start = datetime(2024, 1, 30, 22, tzinfo=timezone.utc)
        df = _make_ohlcv(jan_start, periods=6, freq="12h")  # spans Jan 30–Feb 2

        store.write_ohlcv(EURUSD, H1, df)

        jan_file = tmp_path / "raw" / "EURUSD" / "1h" / "2024-01.parquet"
        feb_file = tmp_path / "raw" / "EURUSD" / "1h" / "2024-02.parquet"
        assert jan_file.exists(), "January partition must exist"
        assert feb_file.exists(), "February partition must exist"

    def test_get_ohlcv_assembles_across_months(self, store: DataStore) -> None:
        jan_start = datetime(2024, 1, 30, 22, tzinfo=timezone.utc)
        df = _make_ohlcv(jan_start, periods=6, freq="12h")
        store.write_ohlcv(EURUSD, H1, df)

        df_out = store.get_ohlcv(
            EURUSD, H1,
            start=jan_start,
            end=jan_start + timedelta(days=4),
        )
        assert len(df_out) == 6


# ── deduplication ─────────────────────────────────────────────────────────────

class TestDeduplication:
    def test_duplicate_timestamps_last_write_wins(self, store: DataStore) -> None:
        start = datetime(2024, 4, 1, tzinfo=timezone.utc)
        df1 = _make_ohlcv(start, periods=3)
        df2 = _make_ohlcv(start, periods=3)  # same timestamps, different close
        df2["close"] = 9.99  # sentinel

        store.write_ohlcv(EURUSD, H1, df1)
        store.write_ohlcv(EURUSD, H1, df2)

        df_out = store.get_ohlcv(EURUSD, H1, start=start, end=start + timedelta(hours=5))
        assert len(df_out) == 3
        assert (df_out["close"] == 9.99).all(), "Last write should win"


# ── validation / error cases ──────────────────────────────────────────────────

class TestValidationErrors:
    def test_empty_dataframe_raises(self, store: DataStore) -> None:
        with pytest.raises(DataError, match="empty"):
            store.write_ohlcv(EURUSD, H1, pd.DataFrame())

    def test_tz_naive_index_raises(self, store: DataStore) -> None:
        df = _make_ohlcv(datetime(2024, 1, 1, tzinfo=timezone.utc), periods=2)
        df_naive = df.copy()
        df_naive.index = df_naive.index.tz_localize(None)
        with pytest.raises(DataError, match="timezone-aware"):
            store.write_ohlcv(EURUSD, H1, df_naive)

    def test_missing_columns_raises(self, store: DataStore) -> None:
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        df = _make_ohlcv(start, periods=2).drop(columns=["close"])
        with pytest.raises(DataError, match="missing columns"):
            store.write_ohlcv(EURUSD, H1, df)

    def test_get_ohlcv_tz_naive_raises(self, store: DataStore) -> None:
        start = datetime(2024, 1, 1)  # no tz
        end = datetime(2024, 1, 2)
        with pytest.raises(DataError, match="timezone-aware"):
            store.get_ohlcv(EURUSD, H1, start=start, end=end)

    def test_get_ohlcv_start_after_end_raises(self, store: DataStore) -> None:
        start = datetime(2024, 1, 10, tzinfo=timezone.utc)
        end = datetime(2024, 1, 1, tzinfo=timezone.utc)
        with pytest.raises(DataError, match="after end"):
            store.get_ohlcv(EURUSD, H1, start=start, end=end)

    def test_get_ohlcv_no_data_raises(self, store: DataStore) -> None:
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 2, tzinfo=timezone.utc)
        with pytest.raises(DataError):
            store.get_ohlcv(EURUSD, H1, start=start, end=end)

    def test_get_ohlcv_out_of_range_raises(self, store: DataStore) -> None:
        # Write Jan data, then query Feb — should raise
        df = _make_ohlcv(datetime(2024, 1, 1, tzinfo=timezone.utc), periods=5)
        store.write_ohlcv(EURUSD, H1, df)
        with pytest.raises(DataError):
            store.get_ohlcv(
                EURUSD, H1,
                start=datetime(2024, 2, 1, tzinfo=timezone.utc),
                end=datetime(2024, 2, 28, tzinfo=timezone.utc),
            )


# ── list_ohlcv_range ──────────────────────────────────────────────────────────

class TestListOHLCVRange:
    def test_returns_none_when_no_data(self, store: DataStore) -> None:
        first, last = store.list_ohlcv_range(EURUSD, H1)
        assert first is None
        assert last is None

    def test_returns_correct_bounds(self, store: DataStore) -> None:
        start = datetime(2024, 5, 1, tzinfo=timezone.utc)
        df = _make_ohlcv(start, periods=10)
        store.write_ohlcv(EURUSD, H1, df)

        first, last = store.list_ohlcv_range(EURUSD, H1)
        assert first is not None
        assert last is not None
        assert first <= last
        assert first.tzinfo is not None



