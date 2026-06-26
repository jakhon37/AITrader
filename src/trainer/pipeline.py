"""D09-TRAINER — Offline training pipeline entrypoint."""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

_log = logging.getLogger(__name__)


def run_training(argv: list[str] | None = None) -> int:
    """Delegate to scripts/train_model.py (registry + feature pipeline)."""
    script = Path(__file__).resolve().parents[2] / "scripts" / "train_model.py"
    cmd = [sys.executable, str(script)] + (argv or [])
    return subprocess.call(cmd)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    parser = argparse.ArgumentParser(description="D09 training pipeline")
    parser.add_argument("--symbol", type=str, default=None)
    parser.add_argument("--model-type", type=str, default=None)
    parser.add_argument("--timeframe", type=str, default=None)
    parser.add_argument("--registry", type=str, default="models/registry")
    args, extra = parser.parse_known_args()

    argv: list[str] = []
    if args.symbol:
        argv.extend(["--symbol", args.symbol])
    if args.model_type:
        argv.extend(["--model-type", args.model_type])
    if args.timeframe:
        argv.extend(["--timeframe", args.timeframe])
    if args.registry:
        argv.extend(["--registry", args.registry])
    argv.extend(extra)

    _log.info("trainer_pipeline_start", argv=argv)
    return run_training(argv)


if __name__ == "__main__":
    sys.exit(main())