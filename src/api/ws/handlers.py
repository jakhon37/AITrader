"""Handlers that bridge Core Bus events to WebSockets and State Caches."""

from __future__ import annotations

import json
from pydantic import BaseModel

from src.api import state
from src.api.ws.manager import ws_manager
from src.core.bus import Bus
from src.core.contracts import (
    BusChannel,
    FundamentalSignal,
    OHLCVBar,
    OrderEvent,
    PortfolioState,
    SystemHealthEvent,
    TechnicalSignal,
    TradeSignal,
)


async def forward_to_ws(channel: BusChannel, payload: BaseModel) -> None:
    """Serialize and broadcast a bus payload to WebSocket clients."""
    data = json.loads(payload.model_dump_json())
    await ws_manager.broadcast({"type": channel.value, "data": data})


async def setup_ws_bridge(bus: Bus) -> None:
    """Subscribe handlers to the bus to forward events to WebSockets and cache state."""

    # 1. OHLCV Bar
    async def on_ohlcv_bar(payload: OHLCVBar) -> None:
        await forward_to_ws(BusChannel.OHLCV_BAR, payload)

    # 2. Technical Signal
    async def on_technical_signal(payload: TechnicalSignal) -> None:
        inst_key = payload.instrument.value
        state.latest_technical[inst_key] = payload
        state.add_to_history(state.technical_history, payload)
        await forward_to_ws(BusChannel.TECHNICAL_SIGNAL, payload)

    # 3. Fundamental Signal
    async def on_fundamental_signal(payload: FundamentalSignal) -> None:
        inst_key = payload.instrument.value
        state.latest_fundamental[inst_key] = payload
        state.add_to_history(state.fundamental_history, payload)
        await forward_to_ws(BusChannel.FUNDAMENTAL_SIGNAL, payload)

    # 4. Trade Signal (Decision combiner)
    async def on_trade_signal(payload: TradeSignal) -> None:
        state.add_to_history(state.trade_signal_history, payload)
        await forward_to_ws(BusChannel.TRADE_SIGNAL, payload)

    # 5. Order Event
    async def on_order_event(payload: OrderEvent) -> None:
        state.add_to_history(state.order_event_history, payload)
        await forward_to_ws(BusChannel.ORDER_EVENT, payload)

    # 6. Portfolio Update
    async def on_portfolio_update(payload: PortfolioState) -> None:
        state.latest_portfolio = payload
        await forward_to_ws(BusChannel.PORTFOLIO_UPDATE, payload)

    # 7. System Health
    async def on_system_health(payload: SystemHealthEvent) -> None:
        state.add_to_history(state.health_history, payload)
        await forward_to_ws(BusChannel.SYSTEM_HEALTH, payload)

    # Subscribe all handlers to the bus
    await bus.subscribe(BusChannel.OHLCV_BAR, on_ohlcv_bar)
    await bus.subscribe(BusChannel.TECHNICAL_SIGNAL, on_technical_signal)
    await bus.subscribe(BusChannel.FUNDAMENTAL_SIGNAL, on_fundamental_signal)
    await bus.subscribe(BusChannel.TRADE_SIGNAL, on_trade_signal)
    await bus.subscribe(BusChannel.ORDER_EVENT, on_order_event)
    await bus.subscribe(BusChannel.PORTFOLIO_UPDATE, on_portfolio_update)
    await bus.subscribe(BusChannel.SYSTEM_HEALTH, on_system_health)
