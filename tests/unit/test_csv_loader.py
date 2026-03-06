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


def test_load_ohlcv_csv_with_explicit_date_column() -> None:
    """Explicit date_column overrides auto-detect."""
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("dt,open,high,low,close\n")
        f.write("2020-01-01,1.0,1.02,0.99,1.01\n")
        f.write("2020-01-02,1.01,1.03,1.0,1.02\n")
        path = Path(f.name)
    try:
        df = load_ohlcv_csv(path, date_column="dt")
        assert len(df) == 2
        assert df.index[0] == pd.Timestamp("2020-01-01")
    finally:
        path.unlink(missing_ok=True)


def test_load_ohlcv_csv_without_volume() -> None:
    """CSV without volume loads; volume column omitted."""
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("date,open,high,low,close\n")
        f.write("2020-01-01,1.0,1.02,0.99,1.01\n")
        path = Path(f.name)
    try:
        df = load_ohlcv_csv(path)
        assert "volume" not in df.columns
        assert list(df.columns) == ["open", "high", "low", "close"]
    finally:
        path.unlink(missing_ok=True)


def test_load_ohlcv_csv_validate_false_skips_validation() -> None:
    """validate=False loads even if high < low (for raw inspection)."""
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("date,open,high,low,close\n")
        f.write("2020-01-01,1.0,0.98,0.99,0.99\n")  # high < low
        path = Path(f.name)
    try:
        df = load_ohlcv_csv(path, validate=False)
        assert len(df) == 1
    finally:
        path.unlink(missing_ok=True)


def test_load_ohlcv_csv_detects_timestamp_column() -> None:
    """Column named 'timestamp' is detected as date column."""
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("timestamp,open,high,low,close\n")
        f.write("2020-01-01 09:00:00,1.0,1.02,0.99,1.01\n")
        path = Path(f.name)
    try:
        df = load_ohlcv_csv(path)
        assert len(df) == 1
    finally:
        path.unlink(missing_ok=True)
