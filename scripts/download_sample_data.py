#!/usr/bin/env python3
"""
Download real market data for Phase 1 testing.

Uses yfinance to fetch:
- EUR/USD (EURUSD=X)
- Gold (GLD)
- GBP/USD (GBPUSD=X)

Saves to data/raw/ as CSV. Run: python scripts/download_sample_data.py
Requires: pip install -e ".[data]"
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SYMBOLS = {
    "eurusd": "EURUSD=X",
    "gbpusd": "GBPUSD=X",
    "usdjpy": "USDJPY=X",
    "gold": "GLD",
}


def download(symbol: str, ticker: str, days: int = 365 * 2) -> None:
    """Download OHLCV and save to CSV."""
    import pandas as pd

    try:
        import yfinance as yf
    except ImportError:
        print("Install yfinance: pip install -e '.[data]'")
        raise SystemExit(1) from None

    print(f"Downloading {symbol} ({ticker})...")
    data = yf.download(ticker, period=f"{days}d", interval="1d", progress=False)
    if data.empty:
        print(f"  No data for {ticker}")
        return

    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    data = data.rename(columns=str.lower)
    required = ["open", "high", "low", "close"]
    if "volume" in data.columns:
        required.append("volume")
    data = data[[c for c in required if c in data.columns]].dropna(
        subset=["open", "high", "low", "close"]
    )
    data.index.name = "date"
    data = data.sort_index()

    out_dir = Path(__file__).resolve().parent.parent / "data" / "raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{symbol}_daily.csv"
    data.to_csv(out_path)
    print(f"  Saved {len(data)} rows to {out_path}")


def main() -> int:
    for symbol, ticker in SYMBOLS.items():
        try:
            download(symbol, ticker)
        except Exception as e:
            print(f"  Error for {symbol}: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
