"""Unit tests for multi-timeframe data retention and integrity probes."""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.core.contracts import Instrument, Timeframe
from src.data.resample import resample_4h
from src.data.store import DataStore
from src.ops.probes.data_probe import DataProbe
from src.ops.session_helper import expected_bar_count


def test_expected_bar_count_weekly_forex() -> None:
    """Verify expected_bar_count filters weekends correctly for June 2026.

    June 2026 has:
    - 30 days total.
    - 4 full weekends (Saturday and Sunday).
    - Sunday closes/Friday opens (excluding Friday 22:00 to Sunday 22:00).
    """
    # June 2026: 30 days. Weekends are June 6-7, 13-14, 20-21, 27-28.
    # Total weekend days = 8 days.
    # Total weekday days = 22 days.
    # Daily bars expected = 22 bars.
    daily_count = expected_bar_count(Timeframe.D1, 2026, 6)
    assert daily_count == 22

    # Hourly bars: 22 weekdays * 24 hours = 528 hours
    # Plus Sunday trading hours: 4 Sundays * 2 hours (22:00-24:00) = 8 hours
    # Minus Friday non-trading hours: 4 Fridays * 2 hours (22:00-24:00) = 8 hours
    # Total expected hours = 528 hours.
    hourly_count = expected_bar_count(Timeframe.H1, 2026, 6)
    assert hourly_count == 528


def test_resample_4h_edges() -> None:
    """Verify that resample_4h resamples to standard boundaries and drops edge candles."""
    # Generate 10 consecutive hourly bars starting at 00:00 UTC
    idx = pd.date_range(start="2026-06-01 00:00:00", periods=10, freq="1h", tz="UTC")
    df = pd.DataFrame(
        {
            "open": np.arange(10, 20),
            "high": np.arange(15, 25),
            "low": np.arange(5, 15),
            "close": np.arange(12, 22),
            "volume": np.arange(100, 110),
        },
        index=idx,
    )

    # Hourly intervals:
    # 00:00 - 04:00: 4 bars (0, 1, 2, 3) -> Should keep
    # 04:00 - 08:00: 4 bars (4, 5, 6, 7) -> Should keep
    # 08:00 - 10:00: 2 bars (8, 9) -> Incomplete, should drop!
    res = resample_4h(df)

    assert len(res) == 2
    assert pd.Timestamp("2026-06-01 00:00:00", tz="UTC") in res.index
    assert pd.Timestamp("2026-06-01 04:00:00", tz="UTC") in res.index
    assert pd.Timestamp("2026-06-01 08:00:00", tz="UTC") not in res.index


def test_data_store_atomic_write() -> None:
    """Verify DataStore write_ohlcv is atomic via temp file rename."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        store = DataStore(base_dir=tmp_dir)

        # Generate simple data chunk
        idx = pd.date_range(start="2026-06-01 00:00:00", periods=5, freq="1h", tz="UTC")
        df = pd.DataFrame(
            {"open": 1.0, "high": 1.1, "low": 0.9, "close": 1.0, "volume": 100},
            index=idx,
        )

        store.write_ohlcv(Instrument.EURUSD, Timeframe.H1, df)

        partition_file = Path(tmp_dir) / "raw" / "EURUSD" / "1h" / "2026-06.parquet"
        assert partition_file.exists()

        # Check there is no left-over temp file
        temp_file = partition_file.with_suffix(".parquet.tmp")
        assert not temp_file.exists()


def test_data_probe_integrity() -> None:
    """Verify DataProbe correctly flags missing or degraded partitions."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        store = DataStore(base_dir=tmp_dir)
        probe = DataProbe(store, gap_threshold_pct=0.05)

        # 1. Test missing partition
        res = probe.verify_stored_integrity(Instrument.EURUSD, Timeframe.H1, "2026-06")
        assert res["status"] == "missing"
        assert res["gap_pct"] == 1.0

        # 2. Test healthy partition (all 528 bars written for June 2026 H1)
        idx_full = pd.date_range(start="2026-06-01 00:00:00", end="2026-06-30 23:59:59", freq="1h", tz="UTC")
        # Filter weekends using expected_bar_count alignment logic
        is_weekend = (
            (idx_full.weekday == 5) |
            ((idx_full.weekday == 4) & (idx_full.hour >= 22)) |
            ((idx_full.weekday == 6) & (idx_full.hour < 22))
        )
        idx_open = idx_full[~is_weekend]

        df_full = pd.DataFrame(
            {"open": 1.0, "high": 1.1, "low": 0.9, "close": 1.0, "volume": 100},
            index=idx_open,
        )

        store.write_ohlcv(Instrument.EURUSD, Timeframe.H1, df_full)
        res_full = probe.verify_stored_integrity(Instrument.EURUSD, Timeframe.H1, "2026-06")
        assert res_full["status"] == "ok"
        assert res_full["gap_pct"] == 0.0

        # 3. Test degraded partition (delete 100 bars from the partition)
        df_degraded = df_full.iloc[100:].copy()
        store.write_ohlcv(Instrument.EURUSD, Timeframe.H1, df_degraded)
        # Re-write overwrites and cleans up duplicates, so it will drop those 100 bars
        # Wait, since DataStore combines and drops duplicates, to write a truncated dataframe,
        # we can overwrite the file completely. Let's delete the file and write the degraded one.
        partition_file = Path(tmp_dir) / "raw" / "EURUSD" / "1h" / "2026-06.parquet"
        partition_file.unlink()

        store.write_ohlcv(Instrument.EURUSD, Timeframe.H1, df_degraded)
        res_degraded = probe.verify_stored_integrity(Instrument.EURUSD, Timeframe.H1, "2026-06")
        assert res_degraded["status"] == "degraded"
        assert res_degraded["gap_pct"] > 0.05
