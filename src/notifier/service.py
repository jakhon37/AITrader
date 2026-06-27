"""D07-NOTIFIER — Notifier service coordinator.

Subscribes to signal bus channels, processes routing filters and aggregation,
and integrates inbound commands with the Telegram Bot API client.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from src.api.display_prefs import DisplayPrefs
    from src.data.store import DataStore
    from src.execution.store import ExecutionStore
    from src.fundamental.agent import FundamentalAgent
    from src.signals.registry import SignalStores

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
from src.notifier.commands import CommandProcessor
from src.notifier.formatters import (
    format_calendar_briefing,
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
        processor: CommandProcessor | None = None,
        execution_store: Optional["ExecutionStore"] = None,
        fundamental_agent: Optional["FundamentalAgent"] = None,
        data_store: Optional["DataStore"] = None,
        display_prefs: Optional["DisplayPrefs"] = None,
        signal_stores: Optional["SignalStores"] = None,
    ) -> None:
        self.config = config
        self.bus = bus

        notifier_cfg = getattr(config, "notifier", {}).get("telegram", {}) if hasattr(config, "notifier") else None

        self.client = client or TelegramClient()
        self.router = router or MessageRouter(config_dict={"telegram": notifier_cfg} if notifier_cfg else None)
        self.aggregator = aggregator or MessageAggregator(send_callback=self.client.send_message)
        self.display_prefs = display_prefs
        self.signal_stores = signal_stores
        self.processor = processor or CommandProcessor(
            bus=self.bus,
            config=self.config,
            signal_stores=signal_stores,
            execution_store=execution_store,
            fundamental_agent=fundamental_agent,
            data_store=data_store,
            display_prefs=display_prefs,
        )

        self.client.register_inbound_handler(self.handle_inbound_message)
        self._running = False
        self._last_trade_alert: dict[str, tuple[datetime, str]] = {}
        self._trade_alert_cooldown = timedelta(minutes=15)

    def _chart_timezone(self) -> str:
        if self.display_prefs is not None:
            return self.display_prefs.get_chart_timezone()
        return "UTC"

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        await self.client.start()
        await self.bus.subscribe(BusChannel.TRADE_SIGNAL, self.handle_trade_signal)
        await self.bus.subscribe(BusChannel.ORDER_EVENT, self.handle_order_event)
        await self.bus.subscribe(BusChannel.FUNDAMENTAL_SIGNAL, self.handle_fundamental_signal)
        await self.bus.subscribe(BusChannel.SYSTEM_HEALTH, self.handle_system_health)
        await self.bus.subscribe(BusChannel.PORTFOLIO_UPDATE, self.handle_portfolio_update)
        _log.info("notifier_service_started")

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        await self.bus.unsubscribe(BusChannel.TRADE_SIGNAL, self.handle_trade_signal)
        await self.bus.unsubscribe(BusChannel.ORDER_EVENT, self.handle_order_event)
        await self.bus.unsubscribe(BusChannel.FUNDAMENTAL_SIGNAL, self.handle_fundamental_signal)
        await self.bus.unsubscribe(BusChannel.SYSTEM_HEALTH, self.handle_system_health)
        await self.bus.unsubscribe(BusChannel.PORTFOLIO_UPDATE, self.handle_portfolio_update)
        await self.aggregator.cancel_all_timers()
        await self.client.stop()
        _log.info("notifier_service_stopped")

    async def handle_inbound_message(self, message: dict[str, Any]) -> None:
        await self.processor.handle_message(message, self.client.send_message)

    def _should_alert_trade_signal(self, signal: TradeSignal, current: datetime) -> bool:
        if not self.router.should_send_trade_signal(signal, current):
            return False

        inst = signal.instrument.value
        fingerprint = (
            f"{signal.direction.value}:{int(signal.confidence * 100)}:"
            f"{signal.suggested_side.value if signal.suggested_side else 'none'}"
        )
        last = self._last_trade_alert.get(inst)
        if last is not None:
            last_at, last_fp = last
            if (
                fingerprint == last_fp
                and current - last_at < self._trade_alert_cooldown
            ):
                return False

        self._last_trade_alert[inst] = (current, fingerprint)
        return True

    async def handle_trade_signal(self, signal: TradeSignal) -> None:
        current = now()
        if self._should_alert_trade_signal(signal, current):
            text = format_trade_signal(signal, self._chart_timezone())
            await self.client.send_message(text)

    async def handle_order_event(self, event: OrderEvent) -> None:
        if self.router.should_send_order_event(event, now()):
            text = format_order_event(event)
            await self.client.send_message(text)

    async def handle_fundamental_signal(self, signal: FundamentalSignal) -> None:
        current = now()
        fund_cfg = getattr(self.config, "fundamental", None)
        calendar_min = (
            getattr(fund_cfg, "calendar_telegram_min_impact", "high") if fund_cfg else "high"
        )

        if self.router.should_send_calendar_briefing(signal, current, min_impact=calendar_min):
            text = format_calendar_briefing(signal, self._chart_timezone())
            await self.client.send_message(text)
            return

        if self.router.should_send_fundamental_signal(signal, current):
            if self.aggregator.should_send_fundamental(signal, current):
                text = format_fundamental_signal(signal, self._chart_timezone())
                await self.client.send_message(text)

    async def handle_system_health(self, event: SystemHealthEvent) -> None:
        if self.router.should_send_system_health(event, now()):
            if self.aggregator.should_send_health(event, now()):
                text = format_system_health(event, self._chart_timezone())
                await self.client.send_message(text)

    async def handle_portfolio_update(self, state: PortfolioState) -> None:
        """Portfolio snapshots are persisted by ExecutionEngine — no local cache."""
        return