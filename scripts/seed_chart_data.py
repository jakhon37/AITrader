#!/usr/bin/env python3
"""
Seed the DataStore Parquet files with 30 days of mock historical OHLCV data
for EURUSD, GBPUSD, USDJPY, and XAUUSD across all common timeframes.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add src/ to PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np
import pandas as pd

from src.core.contracts import Instrument, Timeframe
from src.data.store import DataStore


def generate_mock_ohlcv(
    start_val: float,
    freq_str: str,
    periods: int,
    volatility: float = 0.001
) -> pd.DataFrame:
    """Generate a realistic random walk for OHLCV data."""
    # Generate timestamp index in UTC
    end_time = datetime.now(timezone.utc)
    # Align to boundary of frequency
    if freq_str.endswith("m"):
        mins = int(freq_str[:-1])
        end_time = end_time.replace(minute=(end_time.minute // mins) * mins, second=0, microsecond=0)
    elif freq_str == "1h":
        end_time = end_time.replace(minute=0, second=0, microsecond=0)
    elif freq_str == "1d":
        end_time = end_time.replace(hour=0, minute=0, second=0, microsecond=0)

    start_time = end_time - timedelta(days=30)
    
    idx = pd.date_range(start=start_time, end=end_time, freq=freq_str, tz="UTC")
    n = len(idx)
    
    # Generate random walk
    returns = np.random.normal(0, volatility, n)
    price_path = start_val * np.exp(np.cumsum(returns))
    
    # Construct OHLCV
    df = pd.DataFrame(index=idx)
    df["close"] = price_path
    
    # Generate open, high, low around close
    noise = np.random.uniform(0.0001, volatility * start_val * 0.5, n)
    df["open"] = df["close"].shift(1).fillna(start_val)
    df["high"] = df[["open", "close"]].max(axis=1) + noise
    df["low"] = df[["open", "close"]].min(axis=1) - noise
    df["volume"] = np.random.randint(100, 10000, n).astype(float)
    
    return df


def main() -> int:
    print("🌱 Seeding historical OHLCV Parquet files...")
    store = DataStore(base_dir="data")
    
    configs = [
        (Instrument.EURUSD, 1.0850, 0.0005),
        (Instrument.GBPUSD, 1.2680, 0.0006),
        (Instrument.USDJPY, 155.40, 0.05),
        (Instrument.XAUUSD, 2345.0, 1.2),
    ]
    
    timeframes = [
        (Timeframe.M1, "1min"),
        (Timeframe.M5, "5min"),
        (Timeframe.M15, "15min"),
        (Timeframe.M30, "30min"),
        (Timeframe.H1, "1h"),
        (Timeframe.H4, "4h"),
        (Timeframe.D1, "1d"),
    ]
    
    for inst, start_val, vol in configs:
        for tf, freq_str in timeframes:
            # Calculate periods for 30 days
            if tf == Timeframe.M1:
                freq = "1min"
            elif tf == Timeframe.M5:
                freq = "5min"
            elif tf == Timeframe.M15:
                freq = "15min"
            elif tf == Timeframe.M30:
                freq = "30min"
            elif tf == Timeframe.H1:
                freq = "1h"
            elif tf == Timeframe.H4:
                freq = "4h"
            else:
                freq = "1d"
                
            print(f"  Generating {inst.value} ({tf.value})...")
            df = generate_mock_ohlcv(start_val, freq, 30, vol)
            store.write_ohlcv(inst, tf, df)
            
    print("✅ Database seeding complete!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
