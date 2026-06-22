"""D07-NOTIFIER — Notifier service coordinator.

Subscribes to signal bus channels, processes routing filters and aggregation,
and integrates inbound commands with the Telegram Bot API client.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from src.core.clock import now
from src.core.config import AppConfig
from src.core.contracts import (
    BusChannel,
    FundamentalSignal,
    OrderEvent,
    PortfolioState,
    SystemHealthEvent,
    TradeSignal,
)
from src.core.logging import get_logger
from src.notifier.aggregator import MessageAggregator
from src.notifier.commands import CommandCache, CommandProcessor
from src.notifier.formatters import (
    format_fundamental_signal,
    format_order_event,
    format_system_health,
    format_trade_signal,
)
from src.notifier.router import MessageRouter
from src.notifier.telegram import TelegramClient

_log = get_logger("D07-NOTIFIER")


class NotifierService:
    """Core service for D07 mapping signal bus channels to Telegram alerts and control updates."""

    def __init__(
        self,
        config: AppConfig,
        bus: Any,
        client: TelegramClient | None = None,
        router: MessageRouter | None = None,
        aggregator: MessageAggregator | None = None,
        cache: CommandCache | None = None,
        processor: CommandProcessor | None = None,
    ) -> None:
        self.config = config
        self.bus = bus

        # Configuration dictionary for routing
        notifier_cfg = getattr(config, "notifier", {}).get("telegram", {}) if hasattr(config, "notifier") else None
        
        self.client = client or TelegramClient()
        self.router = router or MessageRouter(config_dict={"telegram": notifier_cfg} if notifier_cfg else None)
        self.aggregator = aggregator or MessageAggregator(send_callback=self.client.send_message)

        # Cache & command processor initialization
        self.cache = cache or CommandCache()
        self.processor = processor or CommandProcessor(bus=self.bus, config=self.config, cache=self.cache)

        # Subscribe to updates
        self.client.register_inbound_handler(self.handle_inbound_message)

        self._running = False

    async def start(self) -> None:
        """Start client loops and subscribe to relevant bus channels."""
        if self._running:
            return
        self._running = True

        # Start bot HTTP long-polling and outbound queue loops
        await self.client.start()

        # Subscribe to bus channels
        await self.bus.subscribe(BusChannel.TRADE_SIGNAL, self.handle_trade_signal)
        await self.bus.subscribe(BusChannel.ORDER_EVENT, self.handle_order_event)
        await self.bus.subscribe(BusChannel.FUNDAMENTAL_SIGNAL, self.handle_fundamental_signal)
        await self.bus.subscribe(BusChannel.SYSTEM_HEALTH, self.handle_system_health)
        await self.bus.subscribe(BusChannel.PORTFOLIO_UPDATE, self.handle_portfolio_update)

        _log.info("notifier_service_started")

    async def stop(self) -> None:
        """Unsubscribe from bus channels and stop client loops."""
        if not self._running:
            return
        self._running = False

        # Unsubscribe from bus channels
        await self.bus.unsubscribe(BusChannel.TRADE_SIGNAL, self.handle_trade_signal)
        await self.bus.unsubscribe(BusChannel.ORDER_EVENT, self.handle_order_event)
        await self.bus.unsubscribe(BusChannel.FUNDAMENTAL_SIGNAL, self.handle_fundamental_signal)
        await self.bus.unsubscribe(BusChannel.SYSTEM_HEALTH, self.handle_system_health)
        await self.bus.unsubscribe(BusChannel.PORTFOLIO_UPDATE, self.handle_portfolio_update)

        # Shutdown active timers and clients
        await self.aggregator.cancel_all_timers()
        await self.client.stop()

        _log.info("notifier_service_stopped")

    async def handle_inbound_message(self, message: dict[str, Any]) -> None:
        """Callback triggered when an authorized inbound user update is received."""
        await self.processor.handle_message(message, self.client.send_message)

    async def handle_trade_signal(self, signal: TradeSignal) -> None:
        """Route TradeSignals immediately to Telegram (never batched)."""
        self.cache.add_trade_signal(signal)

        if self.router.should_send_trade_signal(signal, now()):
            text = format_trade_signal(signal)
            await self.client.send_message(text)

    async def handle_order_event(self, event: OrderEvent) -> None:
        """Route OrderEvents (fills, cancellations, rejections) to Telegram."""
        if self.router.should_send_order_event(event, now()):
            text = format_order_event(event)
            await self.client.send_message(text)

    async def handle_fundamental_signal(self, signal: FundamentalSignal) -> None:
        """Throttles and routes FundamentalSignals to Telegram."""
        self.cache.add_fundamental_signal(signal)

        if self.router.should_send_fundamental_signal(signal, now()):
            if self.aggregator.should_send_fundamental(signal, now()):
                text = format_fundamental_signal(signal)
                await self.client.send_message(text)

    async def handle_system_health(self, event: SystemHealthEvent) -> None:
        """Throttles and routes SystemHealthEvents to Telegram."""
        self.cache.add_health(event)

        if self.router.should_send_system_health(event, now()):
            if self.aggregator.should_send_health(event, now()):
                text = format_system_health(event)
                await self.client.send_message(text)

    async def handle_portfolio_update(self, state: PortfolioState) -> None:
        """Silently update the local portfolio cache for inbound query commands."""
        self.cache.portfolio_state = state
