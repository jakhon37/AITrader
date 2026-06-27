"""D11-OPS — SQLite persistence for per-division system health (replaces in-memory cache)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.core.contracts import SystemHealthEvent
from src.core.logging import get_logger

_log = get_logger("D11-OPS")


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


class SystemHealthStore:
    """Latest health event per division — survives restarts."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS system_health (
                    division       TEXT PRIMARY KEY,
                    timestamp      TEXT NOT NULL,
                    payload_json   TEXT NOT NULL,
                    updated_at     TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_system_health_timestamp
                    ON system_health (timestamp DESC);
                """
            )

    def upsert(self, event: SystemHealthEvent) -> None:
        now = datetime.now(timezone.utc)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO system_health
                    (division, timestamp, payload_json, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    event.division,
                    _iso(event.timestamp),
                    event.model_dump_json(),
                    _iso(now),
                ),
            )

    def get(self, division: str) -> Optional[SystemHealthEvent]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM system_health WHERE division = ?",
                (division,),
            ).fetchone()
        if row is None:
            return None
        return SystemHealthEvent.model_validate_json(row["payload_json"])

    def get_all(self) -> dict[str, SystemHealthEvent]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM system_health ORDER BY division"
            ).fetchall()
        result: dict[str, SystemHealthEvent] = {}
        for row in rows:
            event = SystemHealthEvent.model_validate_json(row["payload_json"])
            result[event.division] = event
        return result

    def list_recent(self, *, limit: int = 100) -> list[SystemHealthEvent]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json FROM system_health
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            SystemHealthEvent.model_validate_json(row["payload_json"]) for row in rows
        ]