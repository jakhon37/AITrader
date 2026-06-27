"""Unit tests for D11-OPS probes and monitor."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.contracts import (
    Direction,
    Instrument,
    MarketRegime,
    SignalStrength,
    TechnicalSignal,
    Timeframe,
    TimeframeBias,
)
from src.ops.monitor import OpsMonitor
from src.ops.probes.exec_probe import ExecutionProbe
from src.ops.probes.model_probe import ModelRegistryProbe
from src.ops.probes.signal_probe import SignalFlowProbe


def test_exec_probe_counts_audit_events(tmp_path: Path) -> None:
    audit = tmp_path / "audit.jsonl"
    audit.write_text(
        json.dumps({"event_type": "position_open", "timestamp": "2026-06-26T10:00:00+00:00"})
        + "\n"
        + json.dumps({"event_type": "error", "timestamp": "2026-06-26T10:01:00+00:00"})
        + "\n"
    )
    probe = ExecutionProbe(audit_path=audit)
    result = probe.check(drawdown_pct=5.0)
    assert result["status"] == "degraded"
    assert result["event_counts"]["position_open"] == 1
    assert result["event_counts"]["error"] == 1


def test_model_probe_reports_no_prod_when_required(tmp_path: Path) -> None:
    registry = tmp_path / "index.json"
    meta_dir = tmp_path / "metadata"
    meta_dir.mkdir()
    meta_file = meta_dir / "lstm_transformer_v1.json"
    meta_file.write_text(json.dumps({"status": "dev"}))
    registry.write_text(
        json.dumps({"versions": {"lstm_transformer:v1": "metadata/lstm_transformer_v1.json"}})
    )
    result = ModelRegistryProbe(registry_path=registry, require_prod=True).check("lstm_transformer")
    assert result["status"] == "degraded"
    assert result["prod_models"] == []


def test_signal_probe_stale_during_session(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from src.signals.stores import TechnicalSignalStore

    now = datetime(2026, 6, 26, 14, 0, tzinfo=timezone.utc)
    valid_until = now + timedelta(hours=1)
    tech_store = TechnicalSignalStore(tmp_path / "technical.db")
    tech_store.upsert_signal(TechnicalSignal(
        signal_id="sig-1",
        timestamp=now - timedelta(hours=3),
        valid_until=valid_until,
        instrument=Instrument.EURUSD,
        direction=Direction.LONG,
        confidence=0.6,
        strength=SignalStrength.MODERATE,
        regime=MarketRegime.TRENDING,
        confluence_score=0.5,
        per_timeframe=[
            TimeframeBias(
                timeframe=Timeframe.H1,
                direction=Direction.LONG,
                confidence=0.6,
                regime=MarketRegime.TRENDING,
                indicators={"rsi": 55.0},
                support=None,
                resistance=None,
            )
        ],
        primary_tf=Timeframe.H1,
        entry_price=None,
        stop_loss=None,
        take_profit=None,
    ))
    monkeypatch.setattr(
        "src.ops.probes.signal_probe.is_instrument_session_open",
        lambda *_args, **_kwargs: True,
    )
    result = SignalFlowProbe(technical_store=tech_store, stale_minutes=60).check(
        [Instrument.EURUSD], now=now,
    )
    assert result["status"] == "degraded"


@pytest.mark.asyncio
async def test_ops_monitor_publishes_health_event_on_breach() -> None:
    bus = MagicMock()
    bus.publish = AsyncMock()
    store = MagicMock()
    cfg = MagicMock()
    cfg.model.model_type = "lstm_transformer"

    monitor = OpsMonitor(bus, store, cfg, interval_sec=999, alert_cooldown_minutes=0)
    snapshot = {
        "data_freshness": {"status": "degraded", "message": "stale H1 bars"},
        "signal_flow": {"status": "ok"},
        "execution": {"status": "ok"},
        "model_registry": {"status": "ok"},
    }
    await monitor._maybe_publish_alert("degraded", snapshot)
    bus.publish.assert_called_once()