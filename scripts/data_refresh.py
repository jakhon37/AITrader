#!/usr/bin/env python3
"""Modular Dukascopy data refresh CLI (replaces operational use of makedata.sh)."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root / "src"))
sys.path.insert(0, str(_root))

from src.core.config import load_config
from src.core.contracts import Instrument
from src.core.logging import get_logger
from src.data.feeds.dukascopy import DukascopyFeed
from src.data.pipeline.backfill import backfill_instrument
from src.data.pipeline.refresh import refresh_all_enabled, refresh_instrument
from src.data.store import DataStore

_log = get_logger("D02-DATA")


def _parse_date(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh OHLCV data from Dukascopy")
    parser.add_argument(
        "--mode",
        choices=["tail", "full"],
        default="tail",
        help="tail=recent days; full=deep historical backfill",
    )
    parser.add_argument(
        "--instrument",
        "-i",
        action="append",
        choices=[inst.value for inst in Instrument],
        help="Instrument(s) to refresh (default: all enabled in config)",
    )
    parser.add_argument("--all", action="store_true", help="Refresh all enabled instruments")
    parser.add_argument("--start", "-s", help="Explicit start date for full mode (YYYY-MM-DD)")
    parser.add_argument("--end", "-e", help="Explicit end date (default: now)")
    args = parser.parse_args()

    cfg = load_config()
    store = DataStore(base_dir=cfg.data.data_dir)
    feed = DukascopyFeed()

    if args.all or not args.instrument:
        results = refresh_all_enabled(store, feed, cfg, mode=args.mode)
        for sym, rows in results.items():
            print(f"✅ {sym}: {rows} M1 rows refreshed ({args.mode})")
        return 0

    end_dt = _parse_date(args.end) if args.end else datetime.now(timezone.utc)
    for sym in args.instrument:
        inst = Instrument(sym)
        if args.mode == "full" and args.start:
            start_dt = _parse_date(args.start)
            rows = backfill_instrument(store, feed, inst, start_dt, end_dt, resample_higher=True)
        else:
            rows = refresh_instrument(
                store,
                feed,
                inst,
                mode=args.mode,
                tail_days=cfg.data.pipeline.tail_days,
                full_lookback_days=cfg.data.pipeline.full_lookback_days,
            )
        print(f"✅ {sym}: {rows} M1 rows refreshed ({args.mode})")
    return 0


if __name__ == "__main__":
    sys.exit(main())