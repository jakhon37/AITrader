#!/usr/bin/env python3
"""Utility script to generate higher timeframe OHLCV data by resampling 1m data."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from datetime import timezone

# Add src to python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pandas as pd

from src.core.contracts import Instrument, Timeframe
from src.data.store import DataStore


def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Resample 1m OHLCV data to a higher timeframe."""
    resampler = df.resample(rule, closed="left", label="left")
    resampled = pd.DataFrame()
    resampled["open"] = resampler["open"].first()
    resampled["high"] = resampler["high"].max()
    resampled["low"] = resampler["low"].min()
    resampled["close"] = resampler["close"].last()
    resampled["volume"] = resampler["volume"].sum()
    return resampled.dropna()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate higher timeframe OHLCV data by resampling 1m data"
    )
    parser.add_argument(
        "--instrument",
        "-i",
        required=True,
        choices=[inst.value for inst in Instrument],
        help="Instrument to process",
    )
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Force overwrite of existing higher timeframe files",
    )
    
    args = parser.parse_args()
    inst = Instrument(args.instrument)
    
    store = DataStore(base_dir="data")
    
    # Locate all 1m parquet files
    source_dir = store.base_dir / "raw" / inst.value / "1m"
    if not source_dir.exists():
        print(f"❌ Source 1m directory not found: {source_dir}")
        return 1
        
    files = sorted(source_dir.glob("*.parquet"))
    if not files:
        print(f"❌ No 1m parquet files found in: {source_dir}")
        return 1
        
    target_timeframes = [
        (Timeframe.M5, "5min"),
        (Timeframe.M15, "15min"),
        (Timeframe.M30, "30min"),
        (Timeframe.H1, "1h"),
        (Timeframe.H4, "4h"),
        (Timeframe.D1, "1d"),
    ]
    
    print(f"🚀 Generating higher timeframes for {inst.value}")
    print(f"📁 Source: {source_dir}")
    print(f"⏰ Targets: {[tf[0].value for tf in target_timeframes]}")
    print("=" * 60)
    
    for f in files:
        month_key = f.stem  # "YYYY-MM"
        print(f"\n📦 Processing month: {month_key}")
        
        try:
            # Read 1m data
            df_1m = pd.read_parquet(f)
            df_1m.index = pd.to_datetime(df_1m.index, utc=True)
            if df_1m.empty:
                print("  ⏩ Skip: empty file")
                continue
                
            for tf, rule in target_timeframes:
                target_path = store.base_dir / "raw" / inst.value / tf.value / f"{month_key}.parquet"
                if target_path.exists() and not args.force:
                    print(f"  ⏩ Skip {tf.value}: partition already exists.")
                    continue
                    
                # Resample
                df_resampled = resample_ohlcv(df_1m, rule)
                if df_resampled.empty:
                    print(f"  ⚠️ Warning {tf.value}: resampled empty.")
                    continue
                    
                # Write
                store.write_ohlcv(inst, tf, df_resampled)
                print(f"  ✅ Generated {tf.value} ({len(df_resampled)} rows)")
                
        except Exception as e:
            print(f"  ❌ Failed to process {month_key}: {e}")
            
    print("\n🎉 Higher timeframe generation complete!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
