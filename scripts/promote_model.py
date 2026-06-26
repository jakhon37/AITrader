#!/usr/bin/env python3
"""Promote a registered model between dev → staging → prod."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from trainer.models.model_registry import ModelRegistry


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote a model in the registry")
    parser.add_argument("--model-name", required=True, help="e.g. lstm_transformer")
    parser.add_argument("--version", required=True, help="e.g. 20260314_160158")
    parser.add_argument(
        "--to",
        required=True,
        choices=["staging", "prod"],
        help="Target promotion stage",
    )
    parser.add_argument(
        "--registry",
        default="models/registry",
        help="Registry base path",
    )
    parser.add_argument(
        "--demote-current-prod",
        action="store_true",
        default=True,
        help="Demote existing prod model to staging when promoting to prod",
    )
    args = parser.parse_args()

    registry = ModelRegistry(base_path=args.registry)
    key = f"{args.model_name}:{args.version}"
    if key not in registry.index.get("versions", {}):
        print(f"Error: model not found: {key}")
        return 1

    if args.to == "prod" and args.demote_current_prod:
        for other_key in registry.index.get("versions", {}):
            if not other_key.startswith(f"{args.model_name}:"):
                continue
            if other_key == key:
                continue
            other_name, other_ver = other_key.split(":", 1)
            meta = registry.get_metadata(other_name, other_ver)
            if meta.get("status") == "prod":
                registry.promote_model(other_name, other_ver, "staging")
                print(f"Demoted previous prod: {other_key} → staging")

    registry.promote_model(args.model_name, args.version, args.to)
    meta = registry.get_metadata(args.model_name, args.version)
    print(f"Promoted {key} → {args.to}")
    print(f"  metrics: {meta.get('metrics', meta.get('accuracy', 'n/a'))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())