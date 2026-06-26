"""D11-OPS — Background health monitor for the live trading stack."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from src.core.bus import Bus
from src.core.contracts import BusChannel, HealthStatus, Instrument, SystemHealthEvent, Timeframe
from src.core.ids import new_signal_id
from src.core.instruments import get_enabled_instruments
from src.core.logging import get_logger
from src.data.store import DataStore
from src.ops.probes.data_freshness_probe import DataFreshnessProbe
from src.ops.probes.exec_probe import ExecutionProbe
from src.ops.probes.model_probe import ModelRegistryProbe
from src.ops.probes.signal_probe import SignalFlowProbe
from src.ops.division_health import publish_division_heartbeats

_log = get_logger("D11-OPS")


class OpsMonitor:
    """Runs periodic probes and publishes SystemHealthEvent on breaches."""

    def __init__(
        self,
        bus: Bus,
        store: DataStore,
        app_config: Any,
        *,
        interval_sec: float = 60.0,
        alert_cooldown_minutes: float = 10.0,
        model_name: str | None = None,
        scheduler: Any = None,
        notifier_active: bool = False,
        fundamental_active: bool = False,
    ) -> None:
        self._bus = bus
        self._store = store
        self._app_config = app_config
        self._scheduler = scheduler
        self._notifier_active = notifier_active
        self._fundamental_active = fundamental_active
        self._interval_sec = interval_sec
        self._alert_cooldown = timedelta(minutes=alert_cooldown_minutes)
        self._model_name = model_name

        self._data_probe = DataFreshnessProbe(store)
        self._signal_probe = SignalFlowProbe()
        self._exec_probe = ExecutionProbe()
        self._model_probe = ModelRegistryProbe()

        self._running = False
        self._task: Optional[asyncio.Task[None]] = None
        self._last_snapshot: dict[str, Any] = {}
        self._last_alert_at: dict[str, datetime] = {}
        self._drawdown_pct: float | None = None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        # Prime snapshot off the event loop so /api/health/ops never blocks callers.
        asyncio.create_task(self.run_once())
        _log.info("ops_monitor_started", interval_sec=self._interval_sec)

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        _log.info("ops_monitor_stopped")

    def get_snapshot(self) -> dict[str, Any]:
        return dict(self._last_snapshot)

    def _run_probes_sync(
        self,
        *,
        now: datetime,
        enabled: list[Instrument],
        pairs: list[tuple[Instrument, Timeframe]],
        drawdown_pct: float | None,
        scheduler_pairs: dict[str, dict[str, Any]],
        scheduler_error: str | None,
    ) -> dict[str, Any]:
        data_result = self._data_probe.check_all(
            pairs,
            now=now,
            scheduler_pairs=scheduler_pairs,
            scheduler_error=scheduler_error,
        )
        signal_result = self._signal_probe.check(enabled, now=now)
        exec_result = self._exec_probe.check(drawdown_pct=drawdown_pct, now=now)
        model_result = self._model_probe.check(model_name=self._model_name)

        overall = "ok"
        for block in (data_result, signal_result, exec_result, model_result):
            if block["status"] == "down":
                overall = "down"
                break
            if block["status"] == "degraded" and overall != "down":
                overall = "degraded"

        return {
            "timestamp": now.isoformat(),
            "status": overall,
            "data_freshness": data_result,
            "signal_flow": signal_result,
            "execution": exec_result,
            "model_registry": model_result,
        }

    async def run_once(self) -> dict[str, Any]:
        from src.api import state as api_state

        now = datetime.now(timezone.utc)
        enabled = get_enabled_instruments(self._app_config)
        pairs = [(inst, Timeframe.M1) for inst in enabled]

        drawdown_pct = None
        if api_state.latest_portfolio is not None:
            drawdown_pct = api_state.latest_portfolio.drawdown_pct

        scheduler_pairs: dict[str, dict[str, Any]] = {}
        scheduler_error: str | None = None
        if self._scheduler is not None and hasattr(self._scheduler, "get_live_status"):
            live_status = self._scheduler.get_live_status()
            scheduler_pairs = live_status.get("pairs", {})
            scheduler_error = live_status.get("last_error")

        loop = asyncio.get_running_loop()
        snapshot = await loop.run_in_executor(
            None,
            lambda: self._run_probes_sync(
                now=now,
                enabled=enabled,
                pairs=pairs,
                drawdown_pct=drawdown_pct,
                scheduler_pairs=scheduler_pairs,
                scheduler_error=scheduler_error,
            ),
        )
        self._last_snapshot = snapshot

        await publish_division_heartbeats(
            self._bus,
            snapshot,
            notifier_active=self._notifier_active,
            fundamental_active=self._fundamental_active,
        )

        if snapshot["status"] != "ok":
            await self._maybe_publish_alert(snapshot["status"], snapshot)

        return snapshot

    async def _maybe_publish_alert(self, status: str, snapshot: dict[str, Any]) -> None:
        key = f"D11-OPS:{status}"
        now = datetime.now(timezone.utc)
        last = self._last_alert_at.get(key)
        if last and (now - last) < self._alert_cooldown:
            return

        health = HealthStatus.DEGRADED if status == "degraded" else HealthStatus.DOWN
        event = SystemHealthEvent(
            signal_id=new_signal_id(),
            division="D11-OPS",
            status=health,
            timestamp=now,
            message=self._summarize(snapshot),
            metrics={"probe_status": 1.0 if status == "down" else 0.5},
        )
        await self._bus.publish(BusChannel.SYSTEM_HEALTH, event)
        self._last_alert_at[key] = now
        _log.warning("ops_health_alert", status=status, message=event.message)

    def _summarize(self, snapshot: dict[str, Any]) -> str:
        parts: list[str] = []
        for name in ("data_freshness", "signal_flow", "execution", "model_registry"):
            block = snapshot.get(name, {})
            if block.get("status") != "ok":
                parts.append(f"{name}: {block.get('message', block.get('status'))}")
        return "; ".join(parts) if parts else "Ops probe degraded"

    async def _loop(self) -> None:
        while self._running:
            try:
                await self.run_once()
                await asyncio.sleep(self._interval_sec)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                _log.error("ops_monitor_cycle_failed", error=str(exc))
                await asyncio.sleep(self._interval_sec)