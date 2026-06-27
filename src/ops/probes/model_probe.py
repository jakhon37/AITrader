"""D11-OPS — Model registry health checks."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ModelRegistryProbe:
    """Verify a prod model exists and report registry summary."""

    def __init__(
        self,
        registry_path: str | Path = "models/registry/index.json",
        *,
        require_prod: bool = True,
    ) -> None:
        self._registry_path = Path(registry_path)
        self._require_prod = require_prod

    def check(self, model_name: str | None = None) -> dict[str, Any]:
        if not self._registry_path.exists():
            return {
                "status": "degraded",
                "message": f"Registry missing: {self._registry_path}",
                "prod_models": [],
                "total_versions": 0,
            }

        with open(self._registry_path) as handle:
            index = json.load(handle)

        versions = index.get("versions", {})
        prod_models: list[dict[str, Any]] = []
        for key, meta_rel in versions.items():
            if model_name and not key.startswith(f"{model_name}:"):
                continue
            meta_path = self._registry_path.parent / meta_rel
            if not meta_path.exists():
                continue
            with open(meta_path) as mf:
                meta = json.load(mf)
            if meta.get("status") == "prod":
                prod_models.append({
                    "model": key,
                    "trained_at": meta.get("trained_at"),
                    "metrics": meta.get("metrics", {}),
                })

        if prod_models:
            status = "ok"
            message = f"{len(prod_models)} prod model(s)"
        elif self._require_prod:
            status = "degraded"
            message = "No prod model promoted — fusion uses rule-based weights"
        else:
            status = "ok"
            message = (
                f"No prod model (dev mode) — {len(versions)} version(s), "
                "fusion uses rule-based weights"
            )

        return {
            "status": status,
            "message": message,
            "prod_models": prod_models,
            "total_versions": len(versions),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }