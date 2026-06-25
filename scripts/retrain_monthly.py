#!/usr/bin/env python3
"""Monthly retrain and promote if better. Placeholder for Phase 7."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def main() -> int:
    """Entry point."""
    from core.config import AppConfig

    cfg = AppConfig.from_env()
    print(f"Config env: {cfg.env}")
    print("Retrain not implemented yet (Phase 7).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
