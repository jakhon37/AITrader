#!/usr/bin/env python3
"""Generate realistic OHLCV fixture (500 trading days). Run from project root."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

np.random.seed(42)
n = 500
base = 1.10
returns = np.random.randn(n) * 0.005
close = base * np.exp(np.cumsum(returns))
high = close * (1 + np.abs(np.random.randn(n) * 0.002))
low = close * (1 - np.abs(np.random.randn(n) * 0.002))
open_ = np.roll(close, 1)
open_[0] = base
df = pd.DataFrame(
    {
        "open": open_,
        "high": np.maximum(high, np.maximum(open_, close)),
        "low": np.minimum(low, np.minimum(open_, close)),
        "close": close,
        "volume": (np.random.rand(n) * 50000 + 80000).astype(int),
    }
)
df.index = pd.bdate_range("2022-01-03", periods=n)
df.index.name = "date"
out = Path(__file__).parent / "eurusd_500_days.csv"
df.to_csv(out)
print(f"Generated {len(df)} rows -> {out}")
