#!/usr/bin/env python3
"""Train all models. Placeholder for Phase 3."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def main() -> int:
    """Entry point."""
    from config import AppConfig

    cfg = AppConfig.from_env()
    print(f"Config env: {cfg.env}, checkpoint_dir: {cfg.model.checkpoint_dir}")
    print("Training not implemented yet (Phase 3).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
