"""Division health heartbeat tests."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.core.contracts import BusChannel, HealthStatus
from src.ops.division_health import publish_division_heartbeats


@pytest.mark.asyncio
async def test_publish_division_heartbeats() -> None:
    bus = AsyncMock()
    snapshot = {
        "status": "degraded",
        "data_freshness": {"status": "degraded", "message": "Stale M1 data"},
        "signal_flow": {"status": "ok", "message": "Signals flowing"},
        "execution": {"status": "ok", "message": "Execution healthy"},
        "model_registry": {"status": "ok", "message": "Model ok"},
    }

    await publish_division_heartbeats(
        bus,
        snapshot,
        notifier_active=True,
        fundamental_active=True,
    )

    assert bus.publish.await_count >= 8
    calls = [c.args[1] for c in bus.publish.await_args_list if c.args[0] == BusChannel.SYSTEM_HEALTH]
    divisions = {e.division: e.status for e in calls}
    assert divisions["D02-DATA"] == HealthStatus.DEGRADED
    assert divisions["D07-NOTIFIER"] == HealthStatus.OK
    assert divisions["D11-OPS"] == HealthStatus.DEGRADED