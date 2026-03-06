"""Unit tests for point-in-time slicing (no future leakage)."""

from __future__ import annotations

import pandas as pd
import pytest

from data.point_in_time import (
    assert_no_future_leakage,
    lookback_at_time,
    slice_at_time,
)


@pytest.fixture
def sample_series() -> pd.DataFrame:
    """DataFrame with 5 datetime rows."""
    return pd.DataFrame(
        {
            "close": [100.0, 101.0, 102.0, 103.0, 104.0],
        },
        index=pd.DatetimeIndex(
            ["2020-01-01", "2020-01-02", "2020-01-03", "2020-01-04", "2020-01-05"]
        ),
    )


def test_slice_at_time_left_excludes_t(sample_series: pd.DataFrame) -> None:
    """inclusive='left' returns only rows with index < t."""
    t = pd.Timestamp("2020-01-03")
    out = slice_at_time(sample_series, t, inclusive="left")
    assert len(out) == 2
    assert out.index.max() < t


def test_slice_at_time_right_includes_t(sample_series: pd.DataFrame) -> None:
    """inclusive='right' returns rows with index <= t."""
    t = pd.Timestamp("2020-01-03")
    out = slice_at_time(sample_series, t, inclusive="right")
    assert len(out) == 3
    assert out.index.max() == t


def test_slice_at_time_empty_df() -> None:
    """Empty DataFrame returns empty."""
    df = pd.DataFrame(columns=["close"])
    df.index = pd.DatetimeIndex([])
    out = slice_at_time(df, pd.Timestamp("2020-01-01"))
    assert out.empty


def test_lookback_at_time_returns_last_n(sample_series: pd.DataFrame) -> None:
    """lookback_at_time returns at most n rows up to t (exclusive of t when inclusive='left')."""
    t = pd.Timestamp("2020-01-05")
    out = lookback_at_time(sample_series, t, n=3, inclusive="left")
    assert len(out) == 3
    assert out.index.max() < t
    # Last 3 rows before t: 2020-01-02, 01-03, 01-04 -> close 101, 102, 103
    assert list(out["close"]) == [101.0, 102.0, 103.0]


def test_lookback_at_time_fewer_than_n(sample_series: pd.DataFrame) -> None:
    """When fewer than n rows exist before t, return all available."""
    t = pd.Timestamp("2020-01-02")
    out = lookback_at_time(sample_series, t, n=10, inclusive="left")
    # Only 2020-01-01 is before 2020-01-02
    assert len(out) == 1


def test_assert_no_future_leakage_passes() -> None:
    """No timestamp after target -> no error."""
    ts = pd.DatetimeIndex(["2020-01-01", "2020-01-02"])
    assert_no_future_leakage(ts, pd.Timestamp("2020-01-03"))


def test_assert_no_future_leakage_raises() -> None:
    """Any timestamp after target -> AssertionError."""
    ts = pd.DatetimeIndex(["2020-01-01", "2020-01-03"])
    with pytest.raises(AssertionError, match="Future leakage"):
        assert_no_future_leakage(ts, pd.Timestamp("2020-01-02"))
