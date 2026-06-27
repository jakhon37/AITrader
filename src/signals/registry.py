"""Central registry of persisted signal stores — inject once at app startup."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from src.fundamental.signal_store import FundamentalSignalStore
from src.ops.health_store import SystemHealthStore
from src.signals.stores import TechnicalSignalStore, TradeSignalStore

if TYPE_CHECKING:
    from src.execution.store import ExecutionStore


@dataclass
class SignalStores:
    """DB-backed signal and health stores (no in-memory cache for reads)."""

    fundamental: FundamentalSignalStore
    technical: TechnicalSignalStore
    trade: TradeSignalStore
    health: SystemHealthStore
    execution: Optional["ExecutionStore"] = None