#!/usr/bin/env python3
"""Test Dukascopy 1-day vs 1-hour tick APIs separately."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone

import requests

SYMBOL = "EURUSD"


def _urls(symbol: str, when: datetime) -> dict[str, str]:
    y, m, d = when.year, when.month, when.day
    hour = max(0, when.hour - 1)
    base = f"https://datafeed.dukascopy.com/datafeed/{symbol}"
    return {
        "1-day (yesterday)": (
            f"{base}/{(when - timedelta(days=1)).year}/"
            f"{(when - timedelta(days=1)).month - 1:02d}/"
            f"{(when - timedelta(days=1)).day:02d}/BID_candles_min_1.bi5"
        ),
        "1-day (today)": f"{base}/{y}/{m - 1:02d}/{d:02d}/BID_candles_min_1.bi5",
        "1-hour ticks (today)": f"{base}/{y}/{m - 1:02d}/{d:02d}/{hour:02d}h_ticks.bi5",
    }


def _probe(name: str, url: str, timeout: float) -> dict[str, object]:
    try:
        resp = requests.get(url, timeout=timeout)
        size = len(resp.content)
        ok = resp.status_code == 200 and size > 0
        return {
            "name": name,
            "url": url,
            "ok": ok,
            "status": resp.status_code,
            "bytes": size,
            "error": None,
        }
    except Exception as exc:
        return {
            "name": name,
            "url": url,
            "ok": False,
            "status": None,
            "bytes": 0,
            "error": str(exc),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Test Dukascopy daily vs hourly APIs")
    parser.add_argument("--symbol", default=SYMBOL)
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    print(f"Dukascopy API probe @ {now.isoformat()}")
    print(f"Symbol: {args.symbol}  timeout: {args.timeout}s\n")

    all_ok = True
    for name, url in _urls(args.symbol, now).items():
        row = _probe(name, url, args.timeout)
        status = row["status"]
        print(f"[{'PASS' if row['ok'] else 'FAIL'}] {row['name']}")
        print(f"  {row['url']}")
        if row["error"]:
            print(f"  error: {row['error']}")
        else:
            print(f"  http={status}  bytes={row['bytes']}")
        print()
        if not row["ok"]:
            all_ok = False

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())