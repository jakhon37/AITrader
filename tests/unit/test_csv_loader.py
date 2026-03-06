"""Unit tests for CSV loader."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from data.loaders.csv_loader import load_ohlcv_csv


def test_load_ohlcv_csv_from_fixture() -> None:
    """Load sample_ohlcv.csv and check shape and columns."""
    fixtures = Path(__file__).resolve().parent.parent / "fixtures" / "sample_ohlcv.csv"
    if not fixtures.exists():
        pytest.skip("fixtures/sample_ohlcv.csv not found")
    df = load_ohlcv_csv(fixtures)
    assert isinstance(df.index, pd.DatetimeIndex)
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert len(df) == 10
    assert df.index.is_monotonic_increasing


def test_load_ohlcv_csv_nonexistent_raises() -> None:
    """Non-existent path raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError, match="not found"):
        load_ohlcv_csv(Path("/nonexistent/file.csv"))
