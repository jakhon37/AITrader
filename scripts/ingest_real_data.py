#!/usr/bin/env python3
"""
Download real market data from yfinance and save to Parquet partitions
so that the Web UI displays real historical data.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add src/ to PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pandas as pd
import yfinance as yf

from src.core.contracts import Instrument, Timeframe
from src.data.store import DataStore
from src.data.loaders.oanda_historical import OANDAHistoricalLoader

TICKER_MAP = {
    Instrument.EURUSD: "EURUSD=X",
    Instrument.GBPUSD: "GBPUSD=X",
    Instrument.USDJPY: "USDJPY=X",
    Instrument.XAUUSD: "GC=F",
}

# Define what to download: (Timeframe, yfinance_interval, lookback_days)
DOWNLOADS = [
    (Timeframe.D1, "1d", 1825),
    (Timeframe.H1, "1h", 700),  # Will also resample to 4h
    (Timeframe.M30, "30m", 30),
    (Timeframe.M15, "15m", 30),
    (Timeframe.M5, "5m", 30),
    (Timeframe.M1, "1m", 7),
]

def clean_and_format(df: pd.DataFrame) -> pd.DataFrame:
    """Format DataFrame columns and index to match DataStore requirements."""
    if df.empty:
        return df
    
    # Handle MultiIndex columns (when yfinance download returns them)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
        
    df.columns = [str(c).lower() for c in df.columns]
    
    # Keep only OHLCV
    required = ["open", "high", "low", "close", "volume"]
    df = df[[c for c in required if c in df.columns]].dropna(subset=["open", "high", "low", "close"])
    
    # Handle timezone-awareness for index
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")
        
    return df

def resample_to_4h(df: pd.DataFrame) -> pd.DataFrame:
    """Resample 1h DataFrame to 4h."""
    if df.empty:
        return df
    
    resampled = pd.DataFrame()
    resampled['open'] = df['open'].resample('4h').first()
    resampled['high'] = df['high'].resample('4h').max()
    resampled['low'] = df['low'].resample('4h').min()
    resampled['close'] = df['close'].resample('4h').last()
    resampled['volume'] = df['volume'].resample('4h').sum()
    
    return resampled.dropna()

def main() -> int:
    print("🌱 Downloading real market data (OANDA/yfinance fallback) and writing to Parquet store...")
    store = DataStore(base_dir="data")
    loader = OANDAHistoricalLoader()
    
    for inst, ticker in TICKER_MAP.items():
        print(f"\n📈 Processing {inst.value} ({ticker})...")
        for tf, yf_interval, days in DOWNLOADS:
            print(f"  Downloading timeframe {tf.value} (lookback: {days} days)...")
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=days)
            
            try:
                # Use unified OANDAHistoricalLoader with fallback
                df = loader.fetch_history(inst, tf, start_date, end_date)
                
                if df.empty:
                    print(f"    ⚠️ No data returned for {inst.value} ({tf.value})")
                    continue
                    
                df = clean_and_format(df)
                if df.empty:
                    print(f"    ⚠️ Data was empty after cleaning for {inst.value} ({tf.value})")
                    continue
                    
                # Write to store
                store.write_ohlcv(inst, tf, df)
                print(f"    ✅ Saved {len(df)} bars to Parquet.")
                
                # If H1, also resample and write H4
                if tf == Timeframe.H1:
                    print("    Resampling H1 to H4...")
                    df_4h = resample_to_4h(df)
                    if not df_4h.empty:
                        store.write_ohlcv(inst, Timeframe.H4, df_4h)
                        print(f"    ✅ Saved {len(df_4h)} resampled H4 bars to Parquet.")
                        
            except Exception as e:
                print(f"    ❌ Error downloading {inst.value} ({tf.value}): {e}")
                
    print("\n🎉 Real market data ingestion complete!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
