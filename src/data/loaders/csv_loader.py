from __future__ import annotations

from pathlib import Path

import pandas as pd

_REQUIRED = {"open", "high", "low", "close"}
_ALLOWED = _REQUIRED | {"volume", "timestamp"}


def load_ohlcv_csv(
    path: str | Path,
    *,
    date_column: str | None = None,
    validate: bool = True,
) -> pd.DataFrame:
    """Load OHLCV data from a CSV file and return a clean DataFrame.

    Automatically detects:
    - Delimiters (semicolon vs comma)
    - Headers (headed vs headerless)
    - Custom date column names (Local time, Gmt time, etc.)
    - Custom date formats (YYYYMMDD HHMMSS, etc.)
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {path}")

    # 1. Delimiter & Header detection
    sep = ","
    has_header = True

    with open(path, "r", encoding="utf-8") as f:
        first_line = f.readline()

    if ";" in first_line and "," not in first_line:
        sep = ";"

    import re
    first_tokens = [t.strip().lower() for t in first_line.split(sep)]
    ohlc_keywords = {"open", "high", "low", "close", "time", "date", "timestamp"}
    if not any(k in t for t in first_tokens for k in ohlc_keywords):
        has_header = False

    # 2. Read file
    if has_header:
        df = pd.read_csv(path, sep=sep)
    else:
        # Headerless fallback (e.g. HistData 1m)
        temp_df = pd.read_csv(path, sep=sep, nrows=5)
        col_count = len(temp_df.columns)
        if col_count == 6:
            names = ["timestamp", "open", "high", "low", "close", "volume"]
        elif col_count == 5:
            names = ["timestamp", "open", "high", "low", "close"]
        else:
            names = [f"col_{i}" for i in range(col_count)]
            if col_count > 0:
                names[0] = "timestamp"
            for idx, col_name in enumerate(["open", "high", "low", "close"]):
                if idx + 1 < col_count:
                    names[idx + 1] = col_name
        df = pd.read_csv(path, sep=sep, names=names, header=None)

    # 3. Handle DateTime column
    if date_column:
        target_date_col = date_column
    else:
        target_date_col = None
        for col in df.columns:
            col_lower = str(col).lower()
            if any(k in col_lower for k in ("time", "date", "gmt", "local", "timestamp")):
                target_date_col = col
                break
        if not target_date_col and not df.empty:
            target_date_col = df.columns[0]

    if target_date_col:
        # Check if date format is HistData YYYYMMDD HHMMSS
        first_val = str(df[target_date_col].iloc[0]) if not df.empty else ""
        if re.match(r"^\d{8}\s\d{6}", first_val):
            df[target_date_col] = pd.to_datetime(
                df[target_date_col], format="%Y%m%d %H%M%S", errors="coerce"
            )
        else:
            df[target_date_col] = pd.to_datetime(df[target_date_col], errors="coerce")

        df = df.set_index(target_date_col)

    # 4. Clean column names
    lower_cols = {c.lower(): c for c in df.columns}
    renamed = {}
    for canonical in ("open", "high", "low", "close", "volume"):
        for lower, original in lower_cols.items():
            if lower == canonical and original != canonical:
                renamed[original] = canonical
                break
    if renamed:
        df = df.rename(columns=renamed)

    # 5. Drop extra columns
    extra = [c for c in df.columns if c.lower() not in _ALLOWED]
    if extra:
        df = df.drop(columns=extra)

    # 6. Validate
    if validate:
        missing = _REQUIRED - set(df.columns)
        if missing:
            raise ValueError(f"CSV missing required OHLC columns: {sorted(missing)}")
        if "high" in df.columns and "low" in df.columns:
            bad = df["high"] < df["low"]
            if bad.any():
                raise ValueError("CSV contains rows where high < low")

    return df
