"""Unit tests for data validation (OHLCV schema)."""

from __future__ import annotations

import pandas as pd
import pytest

from data.validation import (
    normalize_ohlcv_columns,
    raw_ohlcv_schema,
    validate_ohlcv,
)


def test_validate_ohlcv_accepts_valid_df() -> None:
    """Valid OHLCV with datetime index passes."""
    df = pd.DataFrame(
        {
            "open": [1.0, 1.01],
            "high": [1.02, 1.03],
            "low": [0.99, 1.00],
            "close": [1.01, 1.02],
        },
        index=pd.DatetimeIndex(["2020-01-01", "2020-01-02"]),
    )
    validate_ohlcv(df)


def test_validate_ohlcv_rejects_empty() -> None:
    """Empty DataFrame raises."""
    df = pd.DataFrame(columns=["open", "high", "low", "close"])
    df.index = pd.DatetimeIndex([])
    with pytest.raises(ValueError, match="empty"):
        validate_ohlcv(df)


def test_validate_ohlcv_rejects_missing_column() -> None:
    """Missing 'close' raises."""
    df = pd.DataFrame(
        {"open": [1.0], "high": [1.02], "low": [0.99]},
        index=pd.DatetimeIndex(["2020-01-01"]),
    )
    with pytest.raises(ValueError, match="Missing required column"):
        validate_ohlcv(df)


def test_validate_ohlcv_rejects_high_less_than_low() -> None:
    """High < low raises."""
    df = pd.DataFrame(
        {
            "open": [1.0],
            "high": [0.98],
            "low": [0.99],
            "close": [0.99],
        },
        index=pd.DatetimeIndex(["2020-01-01"]),
    )
    with pytest.raises(ValueError, match="High must be >= low"):
        validate_ohlcv(df)


def test_validate_ohlcv_rejects_nan_in_ohlc() -> None:
    """NaN in close raises."""
    df = pd.DataFrame(
        {
            "open": [1.0],
            "high": [1.02],
            "low": [0.99],
            "close": [float("nan")],
        },
        index=pd.DatetimeIndex(["2020-01-01"]),
    )
    with pytest.raises(ValueError, match="contains NaN"):
        validate_ohlcv(df)


def test_validate_ohlcv_rejects_unsorted_index() -> None:
    """Non-monotonic index raises."""
    df = pd.DataFrame(
        {
            "open": [1.0, 1.01],
            "high": [1.02, 1.03],
            "low": [0.99, 1.00],
            "close": [1.01, 1.02],
        },
        index=pd.DatetimeIndex(["2020-01-02", "2020-01-01"]),
    )
    with pytest.raises(ValueError, match="sorted ascending"):
        validate_ohlcv(df)


def test_normalize_ohlcv_columns_lowercase() -> None:
    """Column names normalized to lower-case."""
    df = pd.DataFrame(
        {"Open": [1.0], "High": [1.02], "Low": [0.99], "Close": [1.01]},
        index=pd.DatetimeIndex(["2020-01-01"]),
    )
    out = normalize_ohlcv_columns(df)
    assert list(out.columns) == ["open", "high", "low", "close"]


def test_raw_ohlcv_schema_returns_dict() -> None:
    """Schema doc is a dict with expected keys."""
    schema = raw_ohlcv_schema()
    assert "index" in schema
    assert "columns" in schema
    assert "open" in schema["columns"]


def test_validate_ohlcv_rejects_duplicate_timestamps() -> None:
    """Duplicate index timestamps raise."""
    df = pd.DataFrame(
        {
            "open": [1.0, 1.01],
            "high": [1.02, 1.03],
            "low": [0.99, 1.00],
            "close": [1.01, 1.02],
        },
        index=pd.DatetimeIndex(["2020-01-01", "2020-01-01"]),
    )
    with pytest.raises(ValueError, match="duplicate"):
        validate_ohlcv(df)


def test_validate_ohlcv_rejects_inf() -> None:
    """Inf in OHLC raises."""
    df = pd.DataFrame(
        {
            "open": [1.0],
            "high": [float("inf")],
            "low": [0.99],
            "close": [1.01],
        },
        index=pd.DatetimeIndex(["2020-01-01"]),
    )
    with pytest.raises(ValueError, match="inf"):
        validate_ohlcv(df)


def test_validate_ohlcv_accepts_integer_ohlc() -> None:
    """Integer OHLC (e.g. from some feeds) is valid."""
    df = pd.DataFrame(
        {
            "open": [100],
            "high": [102],
            "low": [99],
            "close": [101],
        },
        index=pd.DatetimeIndex(["2020-01-01"]),
    )
    validate_ohlcv(df)


def test_validate_ohlcv_accepts_with_volume() -> None:
    """OHLCV with volume passes."""
    df = pd.DataFrame(
        {
            "open": [1.0],
            "high": [1.02],
            "low": [0.99],
            "close": [1.01],
            "volume": [100000],
        },
        index=pd.DatetimeIndex(["2020-01-01"]),
    )
    validate_ohlcv(df)


def test_validate_ohlcv_rejects_non_dataframe() -> None:
    """Non-DataFrame raises."""
    with pytest.raises(ValueError, match="DataFrame"):
        validate_ohlcv({"open": [1.0]})  # type: ignore[arg-type]
