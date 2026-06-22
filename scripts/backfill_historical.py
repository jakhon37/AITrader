#!/usr/bin/env python3
"""Idempotent, resumable, and rate-limit aware historical data backfill script."""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add src to python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pandas as pd

from src.core.contracts import Instrument, Timeframe
from src.core.logging import get_logger
from src.data.loaders.oanda_historical import OANDAHistoricalLoader
from src.data.store import DataStore

_log = get_logger("D02-DATA")


def parse_date(date_str: str) -> datetime:
    """Parse date string to UTC datetime."""
    dt = datetime.fromisoformat(date_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill historical market data into the Parquet store"
    )
    parser.add_argument(
        "--instruments",
        "-i",
        nargs="+",
        choices=[inst.value for inst in Instrument],
        help="Instruments to backfill (default: all)",
    )
    parser.add_argument(
        "--timeframes",
        "-t",
        nargs="+",
        choices=[tf.value for tf in Timeframe],
        help="Timeframes to backfill (default: 5m 15m 30m 1h 4h 1d)",
    )
    parser.add_argument(
        "--start",
        "-s",
        required=True,
        help="Start date (YYYY-MM-DD or ISO 8601)",
    )
    parser.add_argument(
        "--end",
        "-e",
        help="End date (default: now)",
    )
    parser.add_argument(
        "--csv-file",
        help="Path to an external CSV file (e.g. from Dukascopy/HistData) to import instead of downloading",
    )
    
    args = parser.parse_args()
    
    # Resolve instruments
    instruments = (
        [Instrument(i) for i in args.instruments]
        if args.instruments
        else list(Instrument)
    )
    
    # Resolve timeframes (default to standard analytical timeframes)
    timeframes = (
        [Timeframe(t) for t in args.timeframes]
        if args.timeframes
        else [Timeframe.M5, Timeframe.M15, Timeframe.M30, Timeframe.H1, Timeframe.H4, Timeframe.D1]
    )
    
    start_dt = parse_date(args.start)
    end_dt = parse_date(args.end) if args.end else datetime.now(timezone.utc)
    
    store = DataStore(base_dir="data")
    
    # CSV import mode
    if args.csv_file:
        csv_path = Path(args.csv_file)
        if not csv_path.exists():
            print(f"❌ CSV file not found: {csv_path}")
            return 1
            
        if len(instruments) != 1 or len(timeframes) != 1:
            print("❌ CSV import mode requires exactly one instrument and one timeframe to be specified.")
            print("   Example: scripts/backfill_historical.py --csv-file data.csv -i EURUSD -t 15m -s 2024-01-01")
            return 1
            
        inst = instruments[0]
        tf = timeframes[0]
        
        print(f"📂 Importing data from CSV file: {csv_path}")
        print(f"  Target: {inst.value} ({tf.value})")
        print(f"  Filter Range: {start_dt.date()} to {end_dt.date()}")
        print("=" * 60)
        
        try:
            from src.data.loaders.csv_loader import load_ohlcv_csv
            df = load_ohlcv_csv(csv_path)
            
            # Ensure timezone-aware UTC
            if df.index.tz is None:
                df.index = df.index.tz_localize("UTC")
            else:
                df.index = df.index.tz_convert("UTC")
                
            # Filter by date range
            df = df.loc[start_dt:end_dt]
            
            if df.empty:
                print("⚠️ No data found in the specified date range inside the CSV.")
                return 0
                
            store.write_ohlcv(inst, tf, df)
            print(f"✅ Successfully imported {len(df)} bars from CSV into Parquet store.")
            
            # Resample H1 to H4 if applicable
            if tf == Timeframe.H1:
                from src.data.resample import resample_4h
                df_4h = resample_4h(df)
                if not df_4h.empty:
                    store.write_ohlcv(inst, Timeframe.H4, df_4h)
                    print(f"✅ Resampled and ingested {len(df_4h)} H4 rows.")
                    
            return 0
        except Exception as e:
            print(f"❌ CSV import failed: {e}")
            return 1
            
    print("🚀 HISTORICAL BACKFILL MANAGER")
    print(f"  Range:       {start_dt.date()} to {end_dt.date()}")
    print(f"  Instruments: {[i.value for i in instruments]}")
    print(f"  Timeframes:  {[t.value for t in timeframes]}")
    print("=" * 60)
    
    loader = OANDAHistoricalLoader()
    
    # Generate list of monthly periods to backfill
    months = pd.date_range(start=start_dt, end=end_dt, freq="MS", tz="UTC")
    if len(months) == 0:
        months = pd.DatetimeIndex([start_dt])
        
    for inst in instruments:
        for tf in timeframes:
            # 4h is resampled, we will backfill H1 and resample H4 dynamically
            if tf == Timeframe.H4:
                continue
                
            print(f"\n📈 Processing {inst.value} ({tf.value})...")
            
            for m in months:
                # Calculate month bounds
                month_start = m.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                # Last day of month (subtract 1 second to make it exclusive)
                if month_start.month == 12:
                    month_end = month_start.replace(year=month_start.year + 1, month=1, day=1) - timedelta(seconds=1)
                else:
                    month_end = month_start.replace(month=month_start.month + 1, day=1) - timedelta(seconds=1)
                
                # Align to query end if needed
                month_start = max(month_start, start_dt)
                month_end = min(month_end, end_dt)
                
                if month_start >= month_end:
                    continue
                
                month_key = m.strftime("%Y-%m")
                partition_path = store._base / "raw" / inst.value / tf.value / f"{month_key}.parquet"
                
                # Check for idempotency / resumability
                # We skip completed months if they already exist and are not incomplete.
                # However, if it is the current month, we overwrite/append to keep it fresh.
                is_current_month = datetime.now(timezone.utc).strftime("%Y-%m") == month_key
                if partition_path.exists() and not is_current_month:
                    try:
                        existing_df = pd.read_parquet(partition_path)
                        if len(existing_df) <= 5:
                            print(f"    ⚠️ Detected incomplete partition ({len(existing_df)} rows) for {month_key}. Redownloading...")
                        else:
                            print(f"    ⏩ Skip completed month: {month_key} (already exists).")
                            continue
                    except Exception:
                        print(f"    ⚠️ Failed to read partition {month_key}. Redownloading...")
                
                print(f"    📥 Downloading {month_key} ({month_start.date()} to {month_end.date()})...")
                
                try:
                    df = loader.fetch_history(inst, tf, month_start, month_end)
                    if df.empty:
                        print("      ⚠️ No data returned.")
                    else:
                        store.write_ohlcv(inst, tf, df)
                        print(f"      ✅ Ingested {len(df)} rows.")
                        
                        # Resample and write H4 if this is H1
                        if tf == Timeframe.H1 and Timeframe.H4 in timeframes:
                            from src.data.resample import resample_4h
                            df_4h = resample_4h(df)
                            if not df_4h.empty:
                                store.write_ohlcv(inst, Timeframe.H4, df_4h)
                                print(f"      ✅ Resampled and ingested {len(df_4h)} H4 rows.")
                                
                    # Pacing to respect rate limits
                    time.sleep(0.5)
                except Exception as e:
                    print(f"      ❌ Failed to backfill: {e}")
                    _log.error("backfill_failed", instrument=inst.value, timeframe=tf.value, month=month_key, error=str(e))
                    
    print("\n🎉 Historical backfill complete!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
