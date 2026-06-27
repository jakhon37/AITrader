"""Handlers that bridge Core Bus events to WebSockets (write-through to SQLite)."""

from __future__ import annotations

import json
from pydantic import BaseModel

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
from src.decision.chart_markers import ChartMarkerStore
from src.fundamental.signal_store import FundamentalSignalStore
from src.ops.health_store import SystemHealthStore
from src.signals.stores import TechnicalSignalStore, TradeSignalStore


async def forward_to_ws(channel: BusChannel, payload: BaseModel) -> None:
    """Serialize and broadcast a bus payload to WebSocket clients."""
    data = json.loads(payload.model_dump_json())
    await ws_manager.broadcast({"type": channel.value, "data": data})


async def setup_ws_bridge(
    bus: Bus,
    *,
    chart_marker_store: ChartMarkerStore | None = None,
    fundamental_signal_store: FundamentalSignalStore | None = None,
    technical_signal_store: TechnicalSignalStore | None = None,
    trade_signal_store: TradeSignalStore | None = None,
    health_store: SystemHealthStore | None = None,
) -> None:
    """Subscribe handlers: persist to DB, then broadcast to WebSocket clients."""

    async def on_ohlcv_bar(payload: OHLCVBar) -> None:
        await forward_to_ws(BusChannel.OHLCV_BAR, payload)

    async def on_technical_signal(payload: TechnicalSignal) -> None:
        if technical_signal_store is not None:
            existing = technical_signal_store.get_latest(payload.instrument)
            if existing is not None and payload.timestamp < existing.timestamp:
                return
            technical_signal_store.upsert_signal(payload)
            technical_signal_store.maintain()
        await forward_to_ws(BusChannel.TECHNICAL_SIGNAL, payload)

    async def on_fundamental_signal(payload: FundamentalSignal) -> None:
        if fundamental_signal_store is not None:
            fundamental_signal_store.upsert(payload)
            fundamental_signal_store.maintain()
        await forward_to_ws(BusChannel.FUNDAMENTAL_SIGNAL, payload)

    async def on_trade_signal(payload: TradeSignal) -> None:
        if trade_signal_store is not None:
            trade_signal_store.upsert_signal(payload)
            trade_signal_store.maintain()
        await forward_to_ws(BusChannel.TRADE_SIGNAL, payload)

        if chart_marker_store is not None:
            marker = chart_marker_store.try_add_from_trade(payload)
            if marker is not None:
                data = json.loads(marker.model_dump_json())
                await ws_manager.broadcast({"type": "chart_marker", "data": data})

    async def on_order_event(payload: OrderEvent) -> None:
        await forward_to_ws(BusChannel.ORDER_EVENT, payload)

    async def on_portfolio_update(payload: PortfolioState) -> None:
        await forward_to_ws(BusChannel.PORTFOLIO_UPDATE, payload)

    async def on_system_health(payload: SystemHealthEvent) -> None:
        if health_store is not None:
            health_store.upsert(payload)
        await forward_to_ws(BusChannel.SYSTEM_HEALTH, payload)

    await bus.subscribe(BusChannel.OHLCV_BAR, on_ohlcv_bar)
    await bus.subscribe(BusChannel.TECHNICAL_SIGNAL, on_technical_signal)
    await bus.subscribe(BusChannel.FUNDAMENTAL_SIGNAL, on_fundamental_signal)
    await bus.subscribe(BusChannel.TRADE_SIGNAL, on_trade_signal)
    await bus.subscribe(BusChannel.ORDER_EVENT, on_order_event)
    await bus.subscribe(BusChannel.PORTFOLIO_UPDATE, on_portfolio_update)
    await bus.subscribe(BusChannel.SYSTEM_HEALTH, on_system_health)