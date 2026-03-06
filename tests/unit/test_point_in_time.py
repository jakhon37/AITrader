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


def test_slice_at_time_t_before_all_data(sample_series: pd.DataFrame) -> None:
    """t before first row returns empty."""
    t = pd.Timestamp("2019-12-31")
    out = slice_at_time(sample_series, t, inclusive="left")
    assert out.empty


def test_slice_at_time_t_after_all_data(sample_series: pd.DataFrame) -> None:
    """t after last row returns full series (left) or full (right)."""
    t = pd.Timestamp("2020-01-10")
    out_left = slice_at_time(sample_series, t, inclusive="left")
    out_right = slice_at_time(sample_series, t, inclusive="right")
    assert len(out_left) == 5
    assert len(out_right) == 5


def test_lookback_at_time_n_zero_returns_empty(sample_series: pd.DataFrame) -> None:
    """n=0 returns empty DataFrame."""
    t = pd.Timestamp("2020-01-05")
    out = lookback_at_time(sample_series, t, n=0, inclusive="left")
    assert out.empty


def test_slice_at_time_does_not_mutate_original(sample_series: pd.DataFrame) -> None:
    """slice_at_time returns copy; original unchanged."""
    orig_len = len(sample_series)
    t = pd.Timestamp("2020-01-03")
    out = slice_at_time(sample_series, t, inclusive="left")
    assert len(sample_series) == orig_len
    assert len(out) == 2
    assert out is not sample_series


def test_slice_at_time_requires_datetime_index() -> None:
    """Non-DatetimeIndex raises."""
    df = pd.DataFrame({"close": [1.0]}, index=[0])
    with pytest.raises(ValueError, match="DatetimeIndex"):
        slice_at_time(df, pd.Timestamp("2020-01-01"))
