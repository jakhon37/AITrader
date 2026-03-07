#!/usr/bin/env python3
"""
Download intraday market data for high-frequency trading.

Uses yfinance to fetch 1-minute, 5-minute, or other intraday data.
Note: Yahoo Finance limits intraday data to the last 60 days.

Saves to data/raw/ as CSV.

Examples:
    # Download 1-minute BTC data
    python scripts/download_intraday_data.py --timeframe 1m --symbols btcusd

    # Download 5-minute data for multiple pairs
    python scripts/download_intraday_data.py --timeframe 5m --symbols eurusd gbpusd btcusd

    # Download 15-minute with custom lookback
    python scripts/download_intraday_data.py --timeframe 15m --days 30 --symbols btcusd
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SYMBOLS = {
    "eurusd": "EURUSD=X",
    "gbpusd": "GBPUSD=X",
    "usdjpy": "USDJPY=X",
    "gold": "GC=F",
    "btcusd": "BTC-USD",
    "ethusd": "ETH-USD",
}


def download(
    symbol: str,
    ticker: str,
    timeframe: str = "1m",
    days: int = 59
) -> None:
    """Download intraday OHLCV and save to CSV.
    
    Args:
        symbol: Internal symbol name (e.g., 'btcusd')
        ticker: Yahoo Finance ticker (e.g., 'BTC-USD')
        timeframe: Timeframe (1m, 2m, 5m, 15m, 30m, 1h)
        days: Number of days to download (max varies by timeframe)
    """
    import pandas as pd

    try:
        import yfinance as yf
    except ImportError:
        print("Install yfinance: pip install -e '.[data]'")
        raise SystemExit(1) from None

    # Yahoo Finance limits by timeframe:
    # 1m: 7 days max, 2m: 60 days, 5m+: 60 days
    if timeframe == "1m":
        days = min(days, 7)
    elif timeframe in ["2m", "5m", "15m", "30m", "60m", "1h"]:
        days = min(days, 59)
    
    print(f"Downloading {symbol} ({ticker}) at {timeframe} for last {days} days...")

    # Download data
    data = yf.download(
        ticker,
        period=f"{days}d",
        interval=timeframe,
        progress=False
    )
    
    if data.empty:
        print(f"  ❌ No data for {ticker}")
        return

    # Clean up columns
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    data = data.rename(columns=str.lower)
    
    # Required columns
    required = ["open", "high", "low", "close"]
    if "volume" in data.columns:
        required.append("volume")
    
    data = data[[c for c in required if c in data.columns]].dropna(
        subset=["open", "high", "low", "close"]
    )
    data.index.name = "date"
    data = data.sort_index()

    # Save to file
    out_dir = Path(__file__).resolve().parent.parent / "data" / "raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{symbol}_{timeframe}.csv"
    data.to_csv(out_path)
    
    print(f"  ✅ Saved {len(data)} bars to {out_path}")
    print(f"     Date range: {data.index[0]} to {data.index[-1]}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download intraday market data from Yahoo Finance"
    )
    parser.add_argument(
        "--timeframe",
        "-t",
        default="1m",
        choices=["1m", "2m", "5m", "15m", "30m", "1h", "1d"],
        help="Timeframe for data (default: 1m)"
    )
    parser.add_argument(
        "--days",
        "-d",
        type=int,
        default=7,
        help="Number of days to download (1m: max 7, others: max 59, default: 7)"
    )
    parser.add_argument(
        "--symbols",
        "-s",
        nargs="+",
        default=["btcusd"],
        help="Symbols to download (default: btcusd)"
    )
    
    args = parser.parse_args()
    
    print(f"\n📊 Downloading {args.timeframe} data for {len(args.symbols)} symbol(s)...")
    print(f"{'='*60}\n")
    
    for symbol_name in args.symbols:
        symbol = symbol_name.lower()
        if symbol not in SYMBOLS:
            print(f"⚠️  Unknown symbol '{symbol}', skipping...")
            continue
        
        ticker = SYMBOLS[symbol]
        try:
            download(symbol, ticker, args.timeframe, args.days)
            print()
        except Exception as e:
            print(f"  ❌ Error for {symbol}: {e}\n")
    
    print(f"{'='*60}")
    print("✅ Download complete!\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
