"""D06-EXECUTION — SQLite persistence for portfolio, positions, and orders."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from src.core.contracts import (
    ExecutionMode,
    Instrument,
    OrderEvent,
    OrderSide,
    PortfolioState,
    PositionSummary,
)
from src.core.logging import get_logger

_log = get_logger("D06-EXECUTION")


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _parse_dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class ExecutionStore:
    """SQLite store for execution state — survives restarts and powers notifier queries."""

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
                CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    execution_mode TEXT NOT NULL,
                    balance REAL NOT NULL,
                    equity REAL NOT NULL,
                    margin_used REAL NOT NULL,
                    free_margin REAL NOT NULL,
                    realized_pnl_today REAL NOT NULL,
                    drawdown_pct REAL NOT NULL,
                    initial_capital REAL,
                    total_realized_pnl REAL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_ts
                    ON portfolio_snapshots (timestamp DESC);

                CREATE TABLE IF NOT EXISTS open_positions (
                    instrument TEXT PRIMARY KEY,
                    side TEXT NOT NULL,
                    size REAL NOT NULL,
                    entry_price REAL NOT NULL,
                    current_price REAL NOT NULL,
                    unrealized_pnl REAL NOT NULL,
                    open_since TEXT NOT NULL,
                    sl REAL,
                    tp REAL,
                    leg_id TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS order_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id TEXT NOT NULL,
                    order_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    instrument TEXT NOT NULL,
                    side TEXT NOT NULL,
                    size REAL NOT NULL,
                    status TEXT NOT NULL,
                    filled_price REAL,
                    filled_at TEXT,
                    execution_mode TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_order_events_ts
                    ON order_events (timestamp DESC);

                CREATE TABLE IF NOT EXISTS closed_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id TEXT NOT NULL,
                    instrument TEXT NOT NULL,
                    side TEXT NOT NULL,
                    size REAL NOT NULL,
                    entry_price REAL NOT NULL,
                    exit_price REAL NOT NULL,
                    realized_pnl REAL NOT NULL,
                    opened_at TEXT NOT NULL,
                    closed_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_closed_trades_closed
                    ON closed_trades (closed_at DESC);
                """
            )

    def save_portfolio_snapshot(
        self,
        state: PortfolioState,
        *,
        initial_capital: Optional[float] = None,
        total_realized_pnl: Optional[float] = None,
    ) -> None:
        """Persist portfolio snapshot and sync open positions table."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO portfolio_snapshots (
                    signal_id, timestamp, execution_mode, balance, equity,
                    margin_used, free_margin, realized_pnl_today, drawdown_pct,
                    initial_capital, total_realized_pnl
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    state.signal_id,
                    _iso(state.timestamp),
                    state.execution_mode.value,
                    state.balance,
                    state.equity,
                    state.margin_used,
                    state.free_margin,
                    state.realized_pnl_today,
                    state.drawdown_pct,
                    initial_capital,
                    total_realized_pnl,
                ),
            )
            conn.execute("DELETE FROM open_positions")
            for pos in state.open_positions:
                conn.execute(
                    """
                    INSERT INTO open_positions (
                        instrument, side, size, entry_price, current_price,
                        unrealized_pnl, open_since, sl, tp, leg_id, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        pos.instrument.value,
                        pos.side.value,
                        pos.size,
                        pos.entry_price,
                        pos.current_price,
                        pos.unrealized_pnl,
                        _iso(pos.open_since),
                        pos.sl,
                        pos.tp,
                        pos.leg_id,
                        _iso(state.timestamp),
                    ),
                )

    def save_order_event(self, event: OrderEvent) -> None:
        order = event.order
        payload = event.model_dump(mode="json")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO order_events (
                    signal_id, order_id, event_type, instrument, side, size,
                    status, filled_price, filled_at, execution_mode,
                    payload_json, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.signal_id,
                    order.order_id,
                    event.event_type,
                    order.instrument.value,
                    order.side.value,
                    order.size,
                    order.status.value,
                    order.filled_price,
                    _iso(order.filled_at) if order.filled_at else None,
                    order.execution_mode.value,
                    json.dumps(payload),
                    _iso(event.timestamp),
                ),
            )

    def record_closed_trade(
        self,
        *,
        signal_id: str,
        instrument: Instrument,
        side: OrderSide,
        size: float,
        entry_price: float,
        exit_price: float,
        realized_pnl: float,
        opened_at: datetime,
        closed_at: datetime,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO closed_trades (
                    signal_id, instrument, side, size, entry_price, exit_price,
                    realized_pnl, opened_at, closed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal_id,
                    instrument.value,
                    side.value,
                    size,
                    entry_price,
                    exit_price,
                    realized_pnl,
                    _iso(opened_at),
                    _iso(closed_at),
                ),
            )

    def get_latest_portfolio(self) -> Optional[PortfolioState]:
        """Return the most recent portfolio snapshot with open positions."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM portfolio_snapshots
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None

            positions = conn.execute(
                "SELECT * FROM open_positions ORDER BY instrument"
            ).fetchall()

        open_positions = [
            PositionSummary(
                instrument=Instrument(p["instrument"]),
                side=OrderSide(p["side"]),
                size=p["size"],
                entry_price=p["entry_price"],
                current_price=p["current_price"],
                unrealized_pnl=p["unrealized_pnl"],
                open_since=_parse_dt(p["open_since"]),
                leg_id=p["leg_id"],
                sl=p["sl"],
                tp=p["tp"],
            )
            for p in positions
        ]

        return PortfolioState(
            signal_id=row["signal_id"],
            timestamp=_parse_dt(row["timestamp"]),
            execution_mode=ExecutionMode(row["execution_mode"]),
            balance=row["balance"],
            equity=row["equity"],
            margin_used=row["margin_used"],
            free_margin=row["free_margin"],
            open_positions=open_positions,
            realized_pnl_today=row["realized_pnl_today"],
            drawdown_pct=row["drawdown_pct"],
        )

    def get_account_meta(self) -> dict[str, Optional[float]]:
        """Return latest capital metadata stored with portfolio snapshots."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT initial_capital, total_realized_pnl
                FROM portfolio_snapshots
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            return {"initial_capital": None, "total_realized_pnl": None}
        return {
            "initial_capital": row["initial_capital"],
            "total_realized_pnl": row["total_realized_pnl"],
        }

    def list_order_events(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json FROM order_events
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [json.loads(r["payload_json"]) for r in rows]

    def list_closed_trades(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM closed_trades
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def has_snapshots(self) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM portfolio_snapshots LIMIT 1"
            ).fetchone()
        return row is not None

    def import_legacy_positions_json(self, path: str | Path) -> bool:
        """One-time migration from data/state/positions.json into SQLite."""
        legacy = Path(path)
        if not legacy.exists() or self.has_snapshots():
            return False

        try:
            data = json.loads(legacy.read_text())
        except Exception as exc:
            _log.warning("execution_store_legacy_import_failed", error=str(exc))
            return False

        cash = float(data.get("cash", 100_000.0))
        initial_capital = float(data.get("initial_capital", cash))
        total_realized = float(data.get("total_realized_pnl", 0.0))
        realized_today = float(data.get("realized_pnl_today", 0.0))
        peak_equity = float(data.get("peak_equity", cash))
        drawdown = (peak_equity - cash) / peak_equity if peak_equity > 0 else 0.0

        open_positions: list[PositionSummary] = []
        for key, val in data.get("positions", {}).items():
            try:
                inst = Instrument(key)
            except ValueError:
                continue
            open_positions.append(
                PositionSummary(
                    instrument=inst,
                    side=OrderSide(val["side"]),
                    size=float(val["size"]),
                    entry_price=float(val["entry_price"]),
                    current_price=float(val["current_price"]),
                    unrealized_pnl=float(val["unrealized_pnl"]),
                    open_since=_parse_dt(val["open_since"]),
                    sl=val.get("sl"),
                    tp=val.get("tp"),
                )
            )

        state = PortfolioState(
            signal_id="legacy-import",
            timestamp=datetime.now(timezone.utc),
            execution_mode=ExecutionMode.PAPER,
            balance=cash,
            equity=cash + sum(p.unrealized_pnl for p in open_positions),
            margin_used=0.0,
            free_margin=cash,
            open_positions=open_positions,
            realized_pnl_today=realized_today,
            drawdown_pct=drawdown,
        )
        self.save_portfolio_snapshot(
            state,
            initial_capital=initial_capital,
            total_realized_pnl=total_realized,
        )
        _log.info(
            "execution_store_legacy_imported",
            path=str(legacy),
            open_positions=len(open_positions),
            balance=cash,
        )
        return True