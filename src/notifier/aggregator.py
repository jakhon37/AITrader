"""D07-NOTIFIER — Message aggregation and rate-throttling.

Batches noisy technical signals over rolling windows and throttles high-frequency
fundamental/health notifications to prevent chat flooding.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List

from src.core.clock import now
from src.core.contracts import FundamentalSignal, HealthStatus, Instrument, SystemHealthEvent
from src.core.logging import get_logger

_log = get_logger("D07-NOTIFIER")


class MessageAggregator:
    """Manages cooldowns for fundamental/health alerts and batches technical signals."""

    def __init__(
        self,
        send_callback: Callable[[str], Any],
        tech_batch_window: float = 60.0,
        fundamental_cooldown_mins: float = 5.0,
        health_cooldown_mins: float = 10.0,
    ) -> None:
        self.send_callback = send_callback
        self.tech_batch_window = tech_batch_window
        self.fundamental_cooldown = timedelta(minutes=fundamental_cooldown_mins)
        self.health_cooldown = timedelta(minutes=health_cooldown_mins)

        # Fundamental signal tracking: maps Instrument -> last sent datetime
        self._last_fund_sent: Dict[Instrument, datetime] = {}

        # System Health degraded alert tracking: maps division -> last sent datetime
        self._last_health_sent: Dict[str, datetime] = {}

        # Technical signals buffer: maps Instrument -> list of signal metrics/descriptions
        self._tech_buffer: Dict[Instrument, List[str]] = {}
        self._tech_timers: Dict[Instrument, asyncio.Task] = {}

    def should_send_fundamental(self, signal: FundamentalSignal, current_time: datetime) -> bool:
        """Throttle fundamental signals to at most 1 per instrument per 5 minutes."""
        last_sent = self._last_fund_sent.get(signal.instrument)
        if last_sent and (current_time - last_sent) < self.fundamental_cooldown:
            _log.debug(
                "aggregator_fundamental_throttled",
                instrument=signal.instrument.value,
                last_sent=last_sent.isoformat(),
            )
            return False

        self._last_fund_sent[signal.instrument] = current_time
        return True

    def should_send_health(self, event: SystemHealthEvent, current_time: datetime) -> bool:
        """Throttle DEGRADED health alerts to at most 1 per division per 10 minutes."""
        # Critical DOWN status is always bypassed and sent immediately
        if event.status == HealthStatus.DOWN:
            return True

        last_sent = self._last_health_sent.get(event.division)
        if last_sent and (current_time - last_sent) < self.health_cooldown:
            _log.debug(
                "aggregator_health_throttled",
                division=event.division,
                last_sent=last_sent.isoformat(),
            )
            return False

        self._last_health_sent[event.division] = current_time
        return True

    async def add_technical_signal(self, instrument: Instrument, text_summary: str) -> None:
        """Buffer technical signals and trigger a flush timer if not already active."""
        self._tech_buffer.setdefault(instrument, []).append(text_summary)

        if instrument not in self._tech_timers:
            self._tech_timers[instrument] = asyncio.create_task(
                self._flush_technical_timer(instrument)
            )

    async def _flush_technical_timer(self, instrument: Instrument) -> None:
        """Wait for the batching window to expire, then aggregate and send buffered signals."""
        await asyncio.sleep(self.tech_batch_window)

        summaries = self._tech_buffer.pop(instrument, [])
        self._tech_timers.pop(instrument, None)

        if not summaries:
            return

        # Format aggregated technical update
        count = len(summaries)
        latest = summaries[-1]
        msg = (
            f"📊 <b>Technical Batch Alert ({instrument.value})</b>\n"
            f"Received {count} technical signal updates in last {self.tech_batch_window:.0f}s.\n"
            f"<b>Latest:</b> {latest}"
        )

        try:
            await self.send_callback(msg)
        except Exception as e:
            _log.error("aggregator_flush_tech_failed", error=str(e))

    async def cancel_all_timers(self) -> None:
        """Cancel any active batching timers. Helpful during shutdown."""
        for inst, task in list(self._tech_timers.items()):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tech_timers.clear()
        self._tech_buffer.clear()
