"""Persisted UI preferences shared between browser and Telegram formatting."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.core.display_time import DEFAULT_DISPLAY_TIMEZONE, resolve_display_timezone
from src.core.logging import get_logger

_log = get_logger("D10-WEBUI")


class DisplayPrefs:
    """Small JSON-backed store for chart display timezone."""

    def __init__(self, data_dir: str | Path) -> None:
        self._path = Path(data_dir) / "state" / "display_prefs.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        try:
            with open(self._path) as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            _log.warning("display_prefs_load_failed", path=str(self._path))
            return {}

    def _save(self) -> None:
        with open(self._path, "w") as handle:
            json.dump(self._cache, handle, indent=2)

    def get_chart_timezone(self) -> str:
        raw = self._cache.get("chart_timezone")
        if not isinstance(raw, str):
            return DEFAULT_DISPLAY_TIMEZONE
        return resolve_display_timezone(raw)

    def set_chart_timezone(self, tz_name: str) -> str:
        resolved = resolve_display_timezone(tz_name)
        self._cache["chart_timezone"] = resolved
        self._save()
        _log.info("chart_timezone_saved", timezone=resolved)
        return resolved