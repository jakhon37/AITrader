"""Thread-safe session state tracking for replay sessions."""

from __future__ import annotations

from datetime import datetime
import json
import threading
from typing import Any, List, Optional

from src.core.contracts import Instrument, Order, PortfolioState, PositionSummary


class ReplaySessionState:
    """Thread-safe container for current replay session state."""

    def __init__(
        self,
        mode: str,
        instrument: Instrument,
        total_bars: int = 0,
        speed: float = 1.0,
        timeframe: str = "1h",
        calculate_indicators: bool = True,
    ) -> None:
        self._lock = threading.Lock()
        self._mode = mode
        self._status = "paused"  # "running" | "paused" | "ended"
        self._current_time = datetime.min
        self._current_bar_index = 0
        self._total_bars = total_bars
        self._speed = speed
        self._instrument = instrument
        self._timeframe = timeframe
        self._calculate_indicators = calculate_indicators
        self._open_positions: List[PositionSummary] = []
        self._trade_history: List[Order] = []
        self._current_portfolio: Optional[PortfolioState] = None

    def update(self, **kwargs: Any) -> None:
        """Update session state fields thread-safely."""
        with self._lock:
            for key, val in kwargs.items():
                private_name = f"_{key}"
                if hasattr(self, private_name):
                    setattr(self, private_name, val)

    @property
    def mode(self) -> str:
        with self._lock:
            return self._mode

    @property
    def status(self) -> str:
        with self._lock:
            return self._status

    @property
    def current_time(self) -> datetime:
        with self._lock:
            return self._current_time

    @property
    def current_bar_index(self) -> int:
        with self._lock:
            return self._current_bar_index

    @property
    def total_bars(self) -> int:
        with self._lock:
            return self._total_bars

    @property
    def speed(self) -> float:
        with self._lock:
            return self._speed

    @property
    def calculate_indicators(self) -> bool:
        with self._lock:
            return self._calculate_indicators

    @property
    def instrument(self) -> Instrument:
        with self._lock:
            return self._instrument

    @property
    def open_positions(self) -> List[PositionSummary]:
        with self._lock:
            return list(self._open_positions)

    @property
    def trade_history(self) -> List[Order]:
        with self._lock:
            return list(self._trade_history)

    @property
    def current_portfolio(self) -> Optional[PortfolioState]:
        with self._lock:
            return self._current_portfolio

    def to_dict(self) -> dict[str, Any]:
        """Convert state to serializable dictionary."""
        with self._lock:
            return {
                "mode": self._mode,
                "status": self._status,
                "current_time": self._current_time.isoformat() if self._current_time else None,
                "current_bar_index": self._current_bar_index,
                "total_bars": self._total_bars,
                "speed": self._speed,
                "instrument": self._instrument.value,
                "timeframe": self._timeframe,
                "calculate_indicators": self._calculate_indicators,
                "open_positions": [json.loads(p.model_dump_json()) for p in self._open_positions],
                "trade_history": [
                    o.model_dump() if hasattr(o, "model_dump")
                    else {
                        "entry_time": o.entry_time.isoformat() if hasattr(o.entry_time, "isoformat") else str(o.entry_time),
                        "exit_time": o.exit_time.isoformat() if hasattr(o.exit_time, "isoformat") else str(o.exit_time),
                        "entry_price": o.entry_price,
                        "exit_price": o.exit_price,
                        "size": o.size,
                        "side": o.side,
                        "pnl": o.pnl,
                        "pnl_pct": o.pnl_pct,
                        "commission": getattr(o, "commission", 0.0),
                    }
                    for o in self._trade_history
                ],
                "current_portfolio": json.loads(self._current_portfolio.model_dump_json()) if self._current_portfolio else None,
            }
