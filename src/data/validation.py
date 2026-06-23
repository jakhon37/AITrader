"""D02-DATA — OHLCV validation utilities.

Enforces schema rules on raw DataFrames before they enter the DataStore or Bus.
D02-DATA rule: fail loud — never silently return empty/unchecked data.

Public API:
    validate_ohlcv(df)            — raises ValueError on any violation
    normalize_ohlcv_columns(df)   — returns df with lowercase column names
    raw_ohlcv_schema()            — returns schema documentation dict
"""

from __future__ import annotations

from typing import Any, Dict

import numpy as np
import pandas as pd

# Required columns (volume is optional)
_REQUIRED_COLUMNS = {"open", "high", "low", "close"}


def normalize_ohlcv_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of df with all column names lowercased.

    Handles mixed-case feeds (e.g. Open, OPEN, open → open).
    Does not modify the original DataFrame.
    """
    result = df.copy()
    result.columns = [c.lower() for c in result.columns]
    return result


def validate_ohlcv(df: object) -> None:
    """Validate an OHLCV DataFrame.  Raises ValueError on any violation.

    Checks (in order):
      1. Must be a pd.DataFrame
      2. Must not be empty
      3. Must have required columns: open, high, low, close
      4. Index must be a DatetimeIndex
      5. Index must be monotonically increasing (sorted ascending)
      6. Index must have no duplicate timestamps
      7. OHLC columns must contain no NaN values
      8. OHLC columns must contain no infinite values
      9. high >= low for every row (OHLC consistency)
    """
    # 1. Type check
    if not isinstance(df, pd.DataFrame):
        raise ValueError(
            f"Expected a DataFrame, got {type(df).__name__!r}."
        )

    # 2. Empty check
    if df.empty:
        raise ValueError("DataFrame is empty — cannot validate an empty OHLCV dataset.")

    # 3. Required columns
    cols = {c.lower() for c in df.columns}
    missing = _REQUIRED_COLUMNS - cols
    if missing:
        raise ValueError(
            f"Missing required column(s): {sorted(missing)}. "
            f"DataFrame has: {sorted(df.columns.tolist())}"
        )

    # Work on lowercased copy to simplify subsequent checks
    df = normalize_ohlcv_columns(df)

    # 4. DatetimeIndex
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError(
            f"Index must be a DatetimeIndex, got {type(df.index).__name__!r}."
        )

    # 5. Monotonic ascending
    if not df.index.is_monotonic_increasing:
        raise ValueError(
            "Index timestamps must be sorted ascending (monotonically increasing). "
            "Call df.sort_index() before validating."
        )

    # 6. No duplicates
    if df.index.duplicated().any():
        dupes = df.index[df.index.duplicated(keep=False)].unique().tolist()
        raise ValueError(
            f"Index has duplicate timestamps: {dupes[:5]}"
            f"{'...' if len(dupes) > 5 else ''}. "
            "Deduplicate before storing."
        )

    ohlc_cols = ["open", "high", "low", "close"]

    # 7. No NaN in OHLC
    for col in ohlc_cols:
        if col in df.columns and df[col].isna().any():
            raise ValueError(
                f"Column '{col}' contains NaN values. "
                "Forward-fill or drop before storing."
            )

    # 8. No inf in OHLC
    for col in ohlc_cols:
        if col in df.columns and np.isinf(df[col].astype(float)).any():
            raise ValueError(
                f"Column '{col}' contains inf values — likely a data feed error."
            )

    # 9. OHLC consistency: high >= low
    bad_rows = df[df["high"] < df["low"]]
    if not bad_rows.empty:
        first = bad_rows.index[0]
        raise ValueError(
            f"High must be >= low for all rows. "
            f"First violation at index {first}: "
            f"high={bad_rows.at[first, 'high']}, low={bad_rows.at[first, 'low']}"
        )


def raw_ohlcv_schema() -> Dict[str, Any]:
    """Return a documentation dict describing the expected OHLCV schema.

    Used by DataStore and csv_loader for self-documentation and tooling.
    """
    return {
        "index": {
            "type": "DatetimeIndex",
            "timezone": "UTC (timezone-aware preferred)",
            "constraint": "monotonically increasing, no duplicates",
        },
        "columns": {
            "open":   {"type": "float", "required": True,  "constraint": ">= 0"},
            "high":   {"type": "float", "required": True,  "constraint": ">= low"},
            "low":    {"type": "float", "required": True,  "constraint": "<= high"},
            "close":  {"type": "float", "required": True,  "constraint": ">= 0"},
            "volume": {"type": "float", "required": False, "constraint": ">= 0"},
        },
        "nan_policy":  "raise — no NaN allowed in open/high/low/close",
        "inf_policy":  "raise — no inf allowed in open/high/low/close",
    }
