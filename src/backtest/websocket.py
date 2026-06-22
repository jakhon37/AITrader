"""WebSocket emitter for D10 browser UI."""

from __future__ import annotations

import logging
import json
from typing import Any, Optional

from src.core.contracts import OHLCVBar, PortfolioState, TechnicalSignal, TradeSignal

logger = logging.getLogger(__name__)


class ReplayWebSocketEmitter:
    """Streams live replay frames to connected WebSocket clients."""

    def __init__(self, ws_url: Optional[str] = None) -> None:
        self.ws_url = ws_url
        logger.info("WebSocket emitter initialized with in-process ws_manager")

    async def emit_frame(
        self,
        bar: OHLCVBar,
        technical_signal: Optional[TechnicalSignal] = None,
        trade_signal: Optional[TradeSignal] = None,
        portfolio_state: Optional[PortfolioState] = None,
        session_state_dict: Optional[dict[str, Any]] = None,
    ) -> None:
        """Emits a ReplayFrame containing the current simulation step details."""
        try:
            from src.api.ws.manager import ws_manager
        except ImportError:
            logger.warning("FastAPI/ws_manager not available. Skipping frame emission.")
            return

        frame = {
            "bar": json.loads(bar.model_dump_json()) if hasattr(bar, "model_dump_json") else bar,
            "technical_signal": json.loads(technical_signal.model_dump_json()) if technical_signal and hasattr(technical_signal, "model_dump_json") else None,
            "trade_signal": json.loads(trade_signal.model_dump_json()) if trade_signal and hasattr(trade_signal, "model_dump_json") else None,
            "portfolio_state": json.loads(portfolio_state.model_dump_json()) if portfolio_state and hasattr(portfolio_state, "model_dump_json") else None,
            "session_state": session_state_dict or {},
        }
        await ws_manager.broadcast({"type": "replay_frame", "data": frame})
