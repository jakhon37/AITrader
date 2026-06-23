"""D02-DATA — Point-in-time slicing utilities.

Prevents look-ahead bias by ensuring all historical data access is gated
by a strict "as of" timestamp.

Rule: features and backtests must ALWAYS use these functions when selecting
historical data. Never call df.loc[: t] directly — it may include t itself
depending on index type and invocation style.

Public API:
    slice_at_time(df, t, inclusive)     — rows strictly/inclusively up to t
    lookback_at_time(df, t, n, inclusive) — last n rows up to t
    assert_no_future_leakage(index, t)  — assertion for test/CI use
"""

from __future__ import annotations

from typing import Literal

import pandas as pd


def slice_at_time(
    df: pd.DataFrame,
    t: pd.Timestamp,
    inclusive: Literal["left", "right"] = "left",
) -> pd.DataFrame:
    """Return rows of df with index < t (left) or index <= t (right).

    Args:
        df:        Source DataFrame with DatetimeIndex.
        t:         Cut-off timestamp.
        inclusive: "left"  → strictly before t  (index < t)
                   "right" → up to and including t (index <= t)

    Returns:
        A copy of the matching rows.  Returns an empty DataFrame (same
        columns) if no rows match.

    Raises:
        ValueError: if df.index is not a DatetimeIndex.
    """
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError(
            f"slice_at_time requires a DatetimeIndex, got {type(df.index).__name__!r}."
        )
    if df.empty:
        return df.copy()

    if inclusive == "left":
        mask = df.index < t
    else:
        mask = df.index <= t

    return df.loc[mask].copy()


def lookback_at_time(
    df: pd.DataFrame,
    t: pd.Timestamp,
    n: int,
    inclusive: Literal["left", "right"] = "left",
) -> pd.DataFrame:
    """Return the last n rows of df with index < t (or <= t if right).

    Equivalent to slice_at_time(df, t, inclusive).iloc[-n:] but handles
    the n=0 edge case cleanly.

    Args:
        df:        Source DataFrame with DatetimeIndex.
        t:         Cut-off timestamp.
        n:         Maximum number of rows to return (tail of the slice).
        inclusive: Same as slice_at_time.

    Returns:
        A copy of at most n rows ending at or before t.

    Raises:
        ValueError: if df.index is not a DatetimeIndex.
    """
    if n == 0:
        return df.iloc[0:0].copy()  # empty, same columns

    sliced = slice_at_time(df, t, inclusive=inclusive)
    return sliced.iloc[-n:].copy()


def assert_no_future_leakage(
    index: pd.DatetimeIndex,
    t: pd.Timestamp,
) -> None:
    """Assert that no timestamp in index is strictly after t.

    Used in tests and CI to verify that a feature DataFrame has no
    look-ahead bias relative to the decision point t.

    Args:
        index: DatetimeIndex of the feature DataFrame being validated.
        t:     The decision timestamp (signal generation time).

    Raises:
        AssertionError: if any timestamp in index > t, with the first
                        offending timestamp in the message.
    """
    future = index[index > t]
    if len(future) > 0:
        raise AssertionError(
            f"Future leakage detected: {len(future)} row(s) after decision "
            f"point {t}. First offending timestamp: {future[0]}."
        )
