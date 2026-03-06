#!/usr/bin/env python3
"""Run paper trading. Placeholder for Phase 6."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def main() -> int:
    """Entry point."""
    from config import AppConfig

    cfg = AppConfig.from_env()
    print(f"Config env: {cfg.env}, broker: {cfg.execution.broker}")
    print("Paper trading not implemented yet (Phase 6).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
