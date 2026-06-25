#!/usr/bin/env python3
"""Purge Yahoo-flat bars and re-fetch good Dukascopy M1 data."""

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
from src.data.feeds.dukascopy import DukascopyFeed
from src.data.pipeline.repair import repair_instrument
from src.data.store import DataStore


def _parse_date(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair corrupt flat OHLCV partitions")
    parser.add_argument("--instrument", "-i", required=True, choices=[x.value for x in Instrument])
    parser.add_argument("--from", dest="from_date", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--to", dest="to_date", help="End date (default: now)")
    args = parser.parse_args()

    cfg = load_config()
    store = DataStore(base_dir=cfg.data.data_dir)
    feed = DukascopyFeed()
    inst = Instrument(args.instrument)
    start = _parse_date(args.from_date)
    end = _parse_date(args.to_date) if args.to_date else datetime.now(timezone.utc)

    print(f"🔧 Repairing {inst.value} from {start.date()} to {end.date()}...")
    result = repair_instrument(store, feed, inst, start, end)
    print(f"✅ Removed {result['removed']} corrupt rows, refetched {result['refetched_m1']} M1 bars")
    return 0


if __name__ == "__main__":
    sys.exit(main())