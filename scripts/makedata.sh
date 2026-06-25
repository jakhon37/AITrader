#!/usr/bin/env bash
# Thin wrapper — operational backfill now lives in scripts/data_refresh.py
set -euo pipefail
cd "$(dirname "$0")/.."

MODE="${1:-tail}"
shift || true

python scripts/data_refresh.py --mode "$MODE" --all "$@"







# python scripts/backfill_historical.py --instruments EURUSD --timeframes 1m --start 2016-01-01 --end 2026-06-21
# python scripts/backfill_historical.py --instruments XAUUSD --timeframes 1m --start 2016-01-01 --end 2026-06-24


# python scripts/generate_higher_timeframes.py --instrument EURUSD
# python scripts/generate_higher_timeframes.py --instrument XAUUSD