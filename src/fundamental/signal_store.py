"""D03-FUNDAMENTAL — SQLite persistence for scored fundamental signals."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from src.core.contracts import FundamentalSignal, Instrument
from src.core.logging import get_logger

_log = get_logger("D03-FUNDAMENTAL")

_DEFAULT_RETENTION_DAYS = 14


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _parse_dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class FundamentalSignalStore:
    """Persist FundamentalSignal history with time-based retention."""

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
                CREATE TABLE IF NOT EXISTS fundamental_signals (
                    signal_id      TEXT PRIMARY KEY,
                    instrument     TEXT NOT NULL,
                    timestamp      TEXT NOT NULL,
                    valid_until    TEXT NOT NULL,
                    payload_json   TEXT NOT NULL,
                    created_at     TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_fund_signals_timestamp
                    ON fundamental_signals (timestamp DESC);

                CREATE INDEX IF NOT EXISTS idx_fund_signals_valid_until
                    ON fundamental_signals (valid_until);
                """
            )

    def upsert(self, signal: FundamentalSignal) -> None:
        """Insert or replace a fundamental signal."""
        now = datetime.now(timezone.utc)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO fundamental_signals
                    (signal_id, instrument, timestamp, valid_until, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    signal.signal_id,
                    signal.instrument.value,
                    _iso(signal.timestamp),
                    _iso(signal.valid_until),
                    signal.model_dump_json(),
                    _iso(now),
                ),
            )
        _log.debug(
            "fundamental_signal_stored",
            signal_id=signal.signal_id,
            instrument=signal.instrument.value,
        )

    def list_recent(
        self,
        *,
        limit: int = 200,
        valid_only: bool = False,
        as_of: Optional[datetime] = None,
        instrument: Optional[Instrument] = None,
    ) -> list[FundamentalSignal]:
        """Return signals newest-first, optionally filtered by validity and instrument."""
        as_of = as_of or datetime.now(timezone.utc)
        query = (
            "SELECT payload_json FROM fundamental_signals WHERE 1=1 "
        )
        params: list[object] = []
        if valid_only:
            query += "AND valid_until >= ? "
            params.append(_iso(as_of))
        if instrument is not None:
            query += "AND instrument = ? "
            params.append(instrument.value)
        query += "ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()

        signals: list[FundamentalSignal] = []
        for row in rows:
            signals.append(FundamentalSignal.model_validate_json(row["payload_json"]))
        return signals

    def get_latest_by_instrument(
        self,
        *,
        as_of: Optional[datetime] = None,
    ) -> dict[str, FundamentalSignal]:
        """Latest valid signal per instrument."""
        as_of = as_of or datetime.now(timezone.utc)
        result: dict[str, FundamentalSignal] = {}
        for signal in self.list_recent(limit=500, valid_only=True, as_of=as_of):
            key = signal.instrument.value
            if key not in result:
                result[key] = signal
        return result

    def purge_expired(self, as_of: Optional[datetime] = None) -> int:
        """Delete signals whose valid_until is in the past."""
        as_of = as_of or datetime.now(timezone.utc)
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM fundamental_signals WHERE valid_until < ?",
                (_iso(as_of),),
            )
            deleted = cursor.rowcount
        if deleted:
            _log.info("fundamental_signals_purged_expired", count=deleted)
        return deleted

    def purge_older_than(self, days: int = _DEFAULT_RETENTION_DAYS) -> int:
        """Delete signals older than N days regardless of validity."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM fundamental_signals WHERE timestamp < ?",
                (_iso(cutoff),),
            )
            deleted = cursor.rowcount
        if deleted:
            _log.info("fundamental_signals_purged_old", count=deleted, days=days)
        return deleted

    def maintain(self, *, retention_days: int = _DEFAULT_RETENTION_DAYS) -> None:
        """Run expiry + age retention."""
        self.purge_expired()
        self.purge_older_than(retention_days)