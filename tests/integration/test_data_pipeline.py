"""Integration tests: load sample → validate → point-in-time slice (no leakage)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from data.loaders.csv_loader import load_ohlcv_csv
from data.point_in_time import assert_no_future_leakage, slice_at_time
from data.validation import validate_ohlcv


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "fixtures"


@pytest.mark.integration
def test_load_validate_slice_no_future_leakage(fixtures_dir: Path) -> None:
    """
    Load CSV → validate OHLCV → slice at a given time.
    Assert that sliced data has no timestamps after the cut-off (point-in-time).
    """
    path = fixtures_dir / "sample_ohlcv.csv"
    if not path.exists():
        pytest.skip("fixtures/sample_ohlcv.csv not found")

    df = load_ohlcv_csv(path)
    validate_ohlcv(df)

    t = pd.Timestamp("2020-01-07")
    past_only = slice_at_time(df, t, inclusive="left")
    assert len(past_only) < len(df)
    assert past_only.index.max() < t

    assert_no_future_leakage(past_only.index, t)


@pytest.mark.integration
def test_full_pipeline_columns_and_index(fixtures_dir: Path) -> None:
    """Loaded data has expected columns and sorted datetime index."""
    path = fixtures_dir / "sample_ohlcv.csv"
    if not path.exists():
        pytest.skip("fixtures/sample_ohlcv.csv not found")

    df = load_ohlcv_csv(path)
    assert "open" in df.columns and "close" in df.columns
    assert isinstance(df.index, pd.DatetimeIndex)
    assert df.index.is_monotonic_increasing


@pytest.mark.integration
def test_500_day_fixture_full_pipeline(fixtures_dir: Path) -> None:
    """
    Load 500-day realistic fixture → validate → point-in-time at multiple cut-offs.
    Verifies no leakage at 10 different timestamps across the series.
    """
    path = fixtures_dir / "eurusd_500_days.csv"
    if not path.exists():
        pytest.skip("fixtures/eurusd_500_days.csv not found (run generate_realistic_fixture.py)")

    df = load_ohlcv_csv(path)
    validate_ohlcv(df)
    assert len(df) >= 400
    assert df.index.is_monotonic_increasing
    assert not df.index.duplicated().any()

    # Test point-in-time at 10 evenly spaced cut-offs
    indices = [len(df) * i // 10 for i in range(1, 10)]
    for i in indices:
        t = df.index[i]
        past_only = slice_at_time(df, t, inclusive="left")
        assert past_only.index.max() < t
        assert_no_future_leakage(past_only.index, t)
        assert len(past_only) == i


@pytest.mark.integration
def test_500_day_fixture_lookback_consistency(fixtures_dir: Path) -> None:
    """lookback_at_time returns correct number of rows and no future data."""
    from data.point_in_time import lookback_at_time

    path = fixtures_dir / "eurusd_500_days.csv"
    if not path.exists():
        pytest.skip("fixtures/eurusd_500_days.csv not found")

    df = load_ohlcv_csv(path)
    t = df.index[100]
    out = lookback_at_time(df, t, n=50, inclusive="left")
    assert len(out) == 50
    assert out.index.max() < t
    assert out.index.min() >= df.index[0]
    assert_no_future_leakage(out.index, t)


@pytest.mark.integration
def test_real_data_if_available() -> None:
    """
    If data/raw/ has downloaded CSVs (from download_sample_data.py), load and validate.
    Skips if no real data present.
    """
    data_dir = Path(__file__).resolve().parent.parent.parent / "data" / "raw"
    if not data_dir.exists():
        pytest.skip("data/raw/ not found (run scripts/download_sample_data.py)")

    csvs = list(data_dir.glob("*.csv"))
    if not csvs:
        pytest.skip("No CSV files in data/raw/")

    for path in csvs[:3]:  # Test up to 3 files
        df = load_ohlcv_csv(path)
        validate_ohlcv(df)
        assert len(df) > 0
        assert df.index.is_monotonic_increasing
        assert not df.index.duplicated().any()
        # Sanity: OHLC in reasonable range for forex/gold
        assert (df["high"] >= df["low"]).all()
        assert (df["close"] > 0).all()
