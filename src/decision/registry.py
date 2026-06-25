"""D05-DECISION — Read-only model registry lookup for live fusion metadata."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from src.core.logging import get_logger

_log = get_logger("D05-DECISION")


def resolve_active_model_version(
    model_name: str,
    registry_path: str | Path = "models/registry/index.json",
) -> Optional[str]:
    """Return prod model version string for TradeSignal.model_version, if promoted."""
    path = Path(registry_path)
    if not path.exists():
        return None

    try:
        with open(path) as f:
            index = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        _log.warning("model_registry_read_failed", error=str(e))
        return None

    versions = index.get("versions", {})
    prefix = f"{model_name}:"
    for key, meta_rel in versions.items():
        if not key.startswith(prefix):
            continue
        meta_path = path.parent / meta_rel
        if not meta_path.exists():
            continue
        try:
            with open(meta_path) as mf:
                meta = json.load(mf)
        except (OSError, json.JSONDecodeError):
            continue
        if meta.get("status") == "prod":
            return key.split(":", 1)[1]

    return None