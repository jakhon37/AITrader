#!/usr/bin/env python3
"""Run backtest (CPCV + walk-forward). Placeholder for Phase 4."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def main() -> int:
    """Entry point."""
    from config import AppConfig

    cfg = AppConfig.from_env()
    print(f"Config env: {cfg.env}")
    print("Backtest not implemented yet (Phase 4).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
