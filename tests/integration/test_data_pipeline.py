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
