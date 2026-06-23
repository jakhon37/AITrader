---
name: validate-data
description: Use this skill when checking data integrity, verifying Parquet files are not corrupted, detecting gaps in OHLCV data, checking if enough historical data exists for training or backtesting, or diagnosing data quality issues before a run.
---

# validate-data

Validates the OHLCV Parquet store for completeness, integrity, and quality. Run before training, backtesting, or replay sessions.

## Quick validation

```bash
# Validate all instruments and timeframes
PYTHONPATH=src CONFIG_DIR=$(pwd)/config python scripts/project_overview.py

# Validate a specific instrument
PYTHONPATH=src CONFIG_DIR=$(pwd)/config python scripts/project_overview.py --instrument EURUSD

# Validate specific instrument + timeframe
PYTHONPATH=src CONFIG_DIR=$(pwd)/config python scripts/project_overview.py --instrument XAUUSD --timeframe 1h
```

## What it checks and what healthy output looks like

```
=== EURUSD / 1h ===
✓ File exists:     data/raw/EURUSD/1h/2022.parquet, 2023.parquet, 2024.parquet
✓ Total bars:      17,520
✓ Date range:      2022-01-03 00:00 UTC → 2024-01-01 00:00 UTC
✓ No duplicate timestamps
✓ No zero prices
✓ No H > L violations
✓ Gaps detected:   48 (all weekend gaps — OK)
✓ Suspicious gaps: 0 (non-weekend gaps > 3h)
✓ Schema:          all columns present, correct dtypes
✓ RESULT:          VALID

=== EURUSD / 4h ===
⚠ Total bars:      4,378 (expected ~4,380 for 2 years — minor, OK)
✓ No suspicious gaps
✓ RESULT:          VALID

=== XAUUSD / 1h ===
✗ Total bars:      1,240 (minimum for CPCV training: 5,000)
⚠ Date range only covers 2023-06-01 → 2024-01-01 (7 months)
! RESULT:          INSUFFICIENT — run data-backfill for longer history
```

## Manual validation in Python

```python
import pandas as pd
import numpy as np
from pathlib import Path

def validate_ohlcv_file(path: str) -> dict:
    df = pd.read_parquet(path)
    issues = []
    
    # Schema check
    required_cols = ["open", "high", "low", "close", "volume"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        issues.append(f"Missing columns: {missing}")
    
    # No duplicates
    dupes = df.index.duplicated().sum()
    if dupes > 0:
        issues.append(f"{dupes} duplicate timestamps")
    
    # HLOC sanity
    bad_hl = (df["high"] < df["low"]).sum()
    if bad_hl > 0:
        issues.append(f"{bad_hl} bars where high < low")
    
    bad_close = ((df["close"] > df["high"]) | (df["close"] < df["low"])).sum()
    if bad_close > 0:
        issues.append(f"{bad_close} bars where close outside high/low")
    
    # Zero prices
    zeros = (df[["open","high","low","close"]] == 0).any(axis=1).sum()
    if zeros > 0:
        issues.append(f"{zeros} bars with zero prices")
    
    # NaN check
    nans = df[["open","high","low","close"]].isna().any(axis=1).sum()
    if nans > 0:
        issues.append(f"{nans} bars with NaN prices")
    
    return {
        "bars": len(df),
        "start": df.index.min(),
        "end": df.index.max(),
        "issues": issues,
        "valid": len(issues) == 0,
    }

# Example usage
result = validate_ohlcv_file("data/raw/EURUSD/1h/2023.parquet")
print(result)
```

## Gap analysis

```python
def find_suspicious_gaps(df: pd.DataFrame, timeframe_minutes: int) -> pd.DataFrame:
    """
    Returns rows where time gap to next row exceeds 3x the expected interval.
    Weekend gaps (Friday close → Monday open) are excluded.
    """
    df = df.sort_index()
    expected_gap = pd.Timedelta(minutes=timeframe_minutes)
    actual_gaps = df.index.to_series().diff()
    
    # Exclude weekend gaps (gap > 40h means it spans a weekend)
    suspicious = actual_gaps[
        (actual_gaps > expected_gap * 3) &
        (actual_gaps < pd.Timedelta(hours=40))
    ]
    return suspicious

# Usage
df = pd.read_parquet("data/raw/EURUSD/1h/2023.parquet")
gaps = find_suspicious_gaps(df, timeframe_minutes=60)
print(f"Suspicious gaps: {len(gaps)}")
print(gaps)
```

## Minimum data requirements by use case

| Use case | Instrument | Timeframe | Minimum bars | Minimum period |
|---|---|---|---|---|
| Technical indicators | any | any | 50 | N/A |
| Regime detection | any | any | 100 | N/A |
| XGBoost training | any | 1h | 2,000 | 3 months |
| LSTM training | any | 1h | 8,000 | 12 months |
| CPCV (6 folds) | any | 1h | 5,000 | 7 months |
| Meaningful backtest | any | 1h | 10,000 | 14 months |
| Walk-forward (4 windows) | any | 1h | 17,000 | 24 months |

## Fix corrupted or missing data

```bash
# Delete a corrupted file and re-download
rm data/raw/EURUSD/1h/2023.parquet
PYTHONPATH=src python scripts/download_sample_data.py \
  --instrument EURUSD \
  --timeframes 1h \
  --start 2023-01-01 \
  --end 2023-12-31

# Fill a gap (re-download overlapping period — dedup handles it)
PYTHONPATH=src python scripts/download_sample_data.py \
  --instrument EURUSD \
  --timeframes 1h \
  --start 2023-06-01 \
  --end 2023-09-01
```

## Validate before a training run

```bash
# This check is built into the training pipeline — it will fail fast if data is insufficient
PYTHONPATH=src CONFIG_DIR=$(pwd)/config python scripts/train_model.py \
  --instrument EURUSD \
  --dry-run   # validates data without running training
```
