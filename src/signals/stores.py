"""SQLite persistence for technical and trade signals (DB is source of truth)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel

from src.core.contracts import Instrument, TechnicalSignal, TradeSignal
from src.core.logging import get_logger

_log = get_logger("D10-WEBUI")

_DEFAULT_RETENTION_DAYS = 14
TModel = TypeVar("TModel", bound=BaseModel)


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


class _SignalStoreBase(Generic[TModel]):
    """Shared SQLite helpers for signal tables."""

    def __init__(
        self,
        db_path: str | Path,
        *,
        table: str,
        model_cls: type[TModel],
        log_name: str,
    ) -> None:
        self._db_path = Path(db_path)
        self._table = table
        self._model_cls = model_cls
        self._log_name = log_name
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self._table} (
                    signal_id      TEXT PRIMARY KEY,
                    instrument     TEXT NOT NULL,
                    timestamp      TEXT NOT NULL,
                    valid_until    TEXT NOT NULL,
                    payload_json   TEXT NOT NULL,
                    created_at     TEXT NOT NULL
                )
                """
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self._table}_timestamp "
                f"ON {self._table} (timestamp DESC)"
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self._table}_valid_until "
                f"ON {self._table} (valid_until)"
            )

    def upsert(self, signal: TModel, *, instrument: str, valid_until: datetime) -> None:
        now = datetime.now(timezone.utc)
        ts = getattr(signal, "timestamp")
        with self._connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {self._table}
                    (signal_id, instrument, timestamp, valid_until, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    signal.signal_id,  # type: ignore[attr-defined]
                    instrument,
                    _iso(ts),
                    _iso(valid_until),
                    signal.model_dump_json(),  # type: ignore[attr-defined]
                    _iso(now),
                ),
            )

    def list_recent(
        self,
        *,
        limit: int = 200,
        valid_only: bool = False,
        as_of: Optional[datetime] = None,
        instrument: Optional[Instrument] = None,
    ) -> list[TModel]:
        as_of = as_of or datetime.now(timezone.utc)
        query = f"SELECT payload_json FROM {self._table} WHERE 1=1 "
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

        return [self._model_cls.model_validate_json(row["payload_json"]) for row in rows]

    def get_latest(
        self,
        instrument: Instrument,
        *,
        as_of: Optional[datetime] = None,
    ) -> Optional[TModel]:
        rows = self.list_recent(
            limit=1,
            instrument=instrument,
            valid_only=True,
            as_of=as_of,
        )
        return rows[0] if rows else None

    def purge_expired(self, as_of: Optional[datetime] = None) -> int:
        as_of = as_of or datetime.now(timezone.utc)
        with self._connect() as conn:
            cursor = conn.execute(
                f"DELETE FROM {self._table} WHERE valid_until < ?",
                (_iso(as_of),),
            )
            deleted = cursor.rowcount
        if deleted:
            _log.info(f"{self._log_name}_purged_expired", count=deleted)
        return deleted

    def purge_older_than(self, days: int = _DEFAULT_RETENTION_DAYS) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        with self._connect() as conn:
            cursor = conn.execute(
                f"DELETE FROM {self._table} WHERE timestamp < ?",
                (_iso(cutoff),),
            )
            deleted = cursor.rowcount
        if deleted:
            _log.info(f"{self._log_name}_purged_old", count=deleted, days=days)
        return deleted

    def maintain(self, *, retention_days: int = _DEFAULT_RETENTION_DAYS) -> None:
        self.purge_expired()
        self.purge_older_than(retention_days)

    def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute(f"SELECT COUNT(*) AS c FROM {self._table}").fetchone()
        return int(row["c"]) if row else 0


class TechnicalSignalStore(_SignalStoreBase[TechnicalSignal]):
    def __init__(self, db_path: str | Path) -> None:
        super().__init__(
            db_path,
            table="technical_signals",
            model_cls=TechnicalSignal,
            log_name="technical_signals",
        )

    def upsert_signal(self, signal: TechnicalSignal) -> None:
        self.upsert(
            signal,
            instrument=signal.instrument.value,
            valid_until=signal.valid_until,
        )


class TradeSignalStore(_SignalStoreBase[TradeSignal]):
    def __init__(self, db_path: str | Path) -> None:
        super().__init__(
            db_path,
            table="trade_signals",
            model_cls=TradeSignal,
            log_name="trade_signals",
        )

    def upsert_signal(self, signal: TradeSignal) -> None:
        self.upsert(
            signal,
            instrument=signal.instrument.value,
            valid_until=signal.valid_until,
        )

    def get_latest_for_instrument(
        self,
        instrument: Instrument,
        *,
        as_of: Optional[datetime] = None,
    ) -> Optional[TradeSignal]:
        return self.get_latest(instrument, as_of=as_of)