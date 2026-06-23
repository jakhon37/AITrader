"""D02-DATA — Base settings and path resolution for DataStore."""

from __future__ import annotations

from pathlib import Path


class BaseStore:
    """Core settings and path mappings for DataStore.

    Initializes data folders and sqlite database paths.
    """

    def __init__(self, base_dir: str | Path = "data") -> None:
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)
        self._news_db_path = self._base / "news.db"
        self._calendar_db_path = self._base / "calendar.db"
        
        # Schema initialization will be triggered here
        self._init_news_schema()
        self._init_calendar_schema()

    @property
    def base_dir(self) -> Path:
        """Return the root path of the data directory tree."""
        return self._base
