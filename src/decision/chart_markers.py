"""D05-DECISION — Persisted chart markers with alternating LONG/SHORT dedup."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.core.contracts import ChartMarker, Direction, Instrument, TradeSignal
from src.core.ids import new_signal_id
from src.core.logging import get_logger

_log = get_logger("D05-DECISION")


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _parse_dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _bar_time_from_trade(trade: TradeSignal) -> datetime:
    """Align marker to the technical bar that triggered the trade signal."""
    technical = trade.sources.technical if trade.sources else None
    if technical is not None:
        return technical.timestamp
    return trade.timestamp


class ChartMarkerStore:
    """SQLite store for chart flip markers — enforces alternating LONG/SHORT."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS chart_markers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    marker_id TEXT NOT NULL UNIQUE,
                    instrument TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    bar_time TEXT NOT NULL,
                    signal_id TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_chart_markers_instrument_bar
                    ON chart_markers (instrument, bar_time DESC);

                CREATE UNIQUE INDEX IF NOT EXISTS idx_chart_markers_instrument_bar_unique
                    ON chart_markers (instrument, bar_time);
                """
            )

    def get_last(self, instrument: Instrument) -> Optional[ChartMarker]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT marker_id, instrument, direction, bar_time, signal_id,
                       confidence, created_at
                FROM chart_markers
                WHERE instrument = ?
                ORDER BY bar_time DESC, id DESC
                LIMIT 1
                """,
                (instrument.value,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_marker(row)

    def try_add_from_trade(self, trade: TradeSignal) -> Optional[ChartMarker]:
        """Record a chart marker only on directional flips (no NEUTRAL, no repeats)."""
        if trade.direction not in (Direction.LONG, Direction.SHORT):
            return None

        instrument = trade.instrument
        bar_time = _bar_time_from_trade(trade)
        last = self.get_last(instrument)

        if last is not None:
            if last.direction == trade.direction:
                _log.debug(
                    "chart_marker_skipped_same_direction",
                    instrument=instrument.value,
                    direction=trade.direction.value,
                )
                return None
            if last.bar_time == bar_time:
                _log.debug(
                    "chart_marker_skipped_same_bar",
                    instrument=instrument.value,
                    bar_time=_iso(bar_time),
                )
                return None

        created_at = datetime.now(timezone.utc)
        marker = ChartMarker(
            marker_id=new_signal_id(),
            instrument=instrument,
            direction=trade.direction,
            bar_time=bar_time,
            signal_id=trade.signal_id,
            confidence=trade.confidence,
            created_at=created_at,
        )

        with self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO chart_markers (
                        marker_id, instrument, direction, bar_time,
                        signal_id, confidence, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        marker.marker_id,
                        instrument.value,
                        trade.direction.value,
                        _iso(bar_time),
                        trade.signal_id,
                        trade.confidence,
                        _iso(created_at),
                    ),
                )
            except sqlite3.IntegrityError:
                _log.debug(
                    "chart_marker_skipped_duplicate_bar",
                    instrument=instrument.value,
                    bar_time=_iso(bar_time),
                )
                return None

        _log.info(
            "chart_marker_recorded",
            instrument=instrument.value,
            direction=trade.direction.value,
            bar_time=_iso(bar_time),
            prior=last.direction.value if last else None,
        )
        return marker

    def list_markers(
        self,
        instrument: Optional[Instrument] = None,
        *,
        limit: int = 200,
    ) -> list[ChartMarker]:
        capped = max(1, min(limit, 500))
        with self._connect() as conn:
            if instrument is not None:
                rows = conn.execute(
                    """
                    SELECT marker_id, instrument, direction, bar_time, signal_id,
                           confidence, created_at
                    FROM chart_markers
                    WHERE instrument = ?
                    ORDER BY bar_time ASC
                    LIMIT ?
                    """,
                    (instrument.value, capped),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT marker_id, instrument, direction, bar_time, signal_id,
                           confidence, created_at
                    FROM chart_markers
                    ORDER BY bar_time ASC
                    LIMIT ?
                    """,
                    (capped,),
                ).fetchall()
        return [self._row_to_marker(r) for r in rows]

    @staticmethod
    def _row_to_marker(row: sqlite3.Row) -> ChartMarker:
        return ChartMarker(
            marker_id=row["marker_id"],
            instrument=Instrument(row["instrument"]),
            direction=Direction(row["direction"]),
            bar_time=_parse_dt(row["bar_time"]),
            signal_id=row["signal_id"],
            confidence=row["confidence"],
            created_at=_parse_dt(row["created_at"]),
        )