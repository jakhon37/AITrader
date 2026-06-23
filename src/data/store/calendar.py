"""D02-DATA — Calendar event storage and retrieval mixin using SQLite."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.core.contracts import Instrument
from src.core.exceptions import DataError
from src.core.logging import get_logger
from src.data.models import RawCalendarEvent

_log = get_logger("D02-DATA")


class CalendarMixin:
    """Mixin for SQLite-based economic calendar storage.

    Expects self._calendar_db_path (Path) to be populated by the base class.
    """

    def _init_calendar_schema(self) -> None:
        """Create calendar SQLite table if it does not yet exist."""
        with sqlite3.connect(self._calendar_db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS calendar (
                    event_id                  TEXT PRIMARY KEY,
                    name                      TEXT NOT NULL,
                    timestamp                 TEXT NOT NULL,  -- UTC ISO-8601
                    impact                    TEXT NOT NULL,  -- low/medium/high
                    instruments               TEXT NOT NULL DEFAULT '[]', -- JSON
                    actual                    REAL,
                    forecast                  REAL,
                    previous                  REAL,
                    surprise_pct              REAL,
                    fetched_at                TEXT NOT NULL,
                    pre_release_notified      INTEGER NOT NULL DEFAULT 0,
                    post_release_notified     INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_calendar_timestamp "
                "ON calendar (timestamp)"
            )

    def write_calendar_events(self, events: list[RawCalendarEvent]) -> None:
        """Upsert calendar events. Existing rows are updated (INSERT OR REPLACE)."""
        if not events:
            return
        rows = [
            (
                e.event_id,
                e.name,
                e.timestamp.isoformat(),
                e.impact,
                json.dumps(e.instruments),
                e.actual,
                e.forecast,
                e.previous,
                e.surprise_pct,
                e.fetched_at.isoformat(),
                int(e.pre_release_notified),
                int(e.post_release_notified),
            )
            for e in events
        ]
        with sqlite3.connect(self._calendar_db_path) as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO calendar
                    (event_id, name, timestamp, impact, instruments,
                     actual, forecast, previous, surprise_pct, fetched_at,
                     pre_release_notified, post_release_notified)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        _log.debug("calendar_written", count=len(rows))

    def get_economic_events(
        self,
        start: datetime,
        end: datetime,
        impact_filter: Optional[str] = None,
    ) -> list[RawCalendarEvent]:
        """Query calendar events in [start, end].

        Parameters
        ----------
        start, end:
            UTC-aware datetimes (event timestamp range).
        impact_filter:
            If provided, one of "low", "medium", "high" — filters to this
            impact level.  If None, all impact levels are returned.

        Returns
        -------
        list[RawCalendarEvent] sorted ascending by timestamp.

        Raises
        ------
        DataError
            If start/end are tz-naive or impact_filter is not a valid level.
        """
        if start.tzinfo is None or end.tzinfo is None:
            raise DataError("get_economic_events: start and end must be UTC-aware.")
        if impact_filter is not None and impact_filter not in ("low", "medium", "high"):
            raise DataError(
                f"get_economic_events: invalid impact_filter {impact_filter!r}. "
                "Must be 'low', 'medium', 'high', or None."
            )

        start_iso = start.astimezone(timezone.utc).isoformat()
        end_iso = end.astimezone(timezone.utc).isoformat()

        query = (
            "SELECT event_id, name, timestamp, impact, instruments, "
            "actual, forecast, previous, surprise_pct, fetched_at, "
            "pre_release_notified, post_release_notified "
            "FROM calendar "
            "WHERE timestamp >= ? AND timestamp <= ? "
        )
        params: list = [start_iso, end_iso]

        if impact_filter:
            query += "AND impact = ? "
            params.append(impact_filter)

        query += "ORDER BY timestamp ASC"

        with sqlite3.connect(self._calendar_db_path) as conn:
            rows = conn.execute(query, params).fetchall()

        events: list[RawCalendarEvent] = []
        for row in rows:
            events.append(
                RawCalendarEvent(
                    event_id=row[0],
                    name=row[1],
                    timestamp=datetime.fromisoformat(row[2]),
                    impact=row[3],  # type: ignore[arg-type]
                    instruments=json.loads(row[4] or "[]"),
                    actual=row[5],
                    forecast=row[6],
                    previous=row[7],
                    surprise_pct=row[8],
                    fetched_at=datetime.fromisoformat(row[9]),
                    pre_release_notified=bool(row[10]),
                    post_release_notified=bool(row[11]),
                )
            )

        _log.debug(
            "calendar_queried",
            start=start.date().isoformat(),
            end=end.date().isoformat(),
            impact=impact_filter or "all",
            count=len(events),
        )
        return events

    def mark_event_notified(
        self,
        event_id: str,
        *,
        pre: bool = False,
        post: bool = False,
    ) -> None:
        """Mark a calendar event as having sent its pre- or post-release notification."""
        if pre:
            col = "pre_release_notified"
        elif post:
            col = "post_release_notified"
        else:
            return
        with sqlite3.connect(self._calendar_db_path) as conn:
            conn.execute(
                f"UPDATE calendar SET {col} = 1 WHERE event_id = ?",  # noqa: S608
                (event_id,),
            )
