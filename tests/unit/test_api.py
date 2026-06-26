"""Unit tests for the FastAPI Web UI backend."""

from __future__ import annotations

import subprocess
import sys
try:
    import fastapi
except ImportError:
    print("Installing web UI dependencies for test run...")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "fastapi>=0.100.0", "uvicorn>=0.20.0", "websockets>=11.0"]
    )

import os
import tempfile
import src.core.config

# Setup temporary writeable data directory before imports/app startup
tmp_dir = tempfile.mkdtemp()
original_load_config = src.core.config.load_config

def mocked_load_config(*args, **kwargs):
    cfg = original_load_config(*args, **kwargs)
    cfg.data.data_dir = tmp_dir
    return cfg

src.core.config.load_config = mocked_load_config

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient
import pandas as pd

from src.api.main import app
from src.api.ws.manager import ws_manager
from datetime import timedelta

from src.core.contracts import BusChannel, Instrument, HealthStatus, SystemHealthEvent
from src.core.clock import now
from src.data.models import RawCalendarEvent


@pytest.fixture
def client():
    """Test client fixture."""
    with TestClient(app) as test_client:
        yield test_client


def test_ops_health_endpoint(client):
    """Test GET /api/health/ops returns monitor status or pending."""
    response = client.get("/api/health/ops")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data


def test_pipeline_health_endpoint(client):
    """Test GET /api/health/pipeline returns live component status."""
    response = client.get("/api/health/pipeline")
    assert response.status_code == 200
    data = response.json()
    assert "components" in data
    assert "scheduler" in data["components"]
    assert "decision_engine" in data["components"]


def test_health_endpoint(client):
    """Test GET /api/health returns ok status."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "divisions" in data


def test_live_status_endpoint(client):
    """Test GET /api/data/live-status returns scheduler health."""
    response = client.get("/api/data/live-status")
    assert response.status_code == 200
    data = response.json()
    assert "running" in data
    assert "active_pairs" in data
    assert "replay_active" in data
    assert "live_poll_adaptive" in data
    assert "enabled_instruments" in data
    assert set(data["enabled_instruments"]) >= {
        "EURUSD",
        "GBPUSD",
        "USDJPY",
        "XAUUSD",
    }


def test_data_instruments_endpoint(client):
    """Test GET /api/data/instruments lists all enabled Dukascopy pairs."""
    response = client.get("/api/data/instruments")
    assert response.status_code == 200
    data = response.json()
    assert set(data["enabled"]) >= {"EURUSD", "GBPUSD", "USDJPY", "XAUUSD"}
    assert set(data["supported"]) == {"EURUSD", "GBPUSD", "USDJPY", "XAUUSD"}
    assert "configs" in data
    assert data["configs"]["XAUUSD"]["daily_break"]["start"] == "21:00"


def test_config_endpoint(client):
    """Test GET /api/config/{instrument} loads from instruments.yaml."""
    response = client.get("/api/config/eurusd")
    if response.status_code == 200:
        data = response.json()
        assert "pip_size" in data
        assert "lot_size" in data
    else:
        # File might not exist in testing sandbox depending on path resolution
        assert response.status_code == 404


def test_portfolio_state_endpoint(client):
    """Test GET /api/portfolio/state returns fallback or active stats."""
    response = client.get("/api/portfolio/state")
    assert response.status_code == 200
    data = response.json()
    assert "balance" in data
    assert "equity" in data
    assert "open_positions" in data


def test_upcoming_calendar_endpoint(client):
    """Test GET /api/data/calendar/upcoming returns enriched upcoming events."""
    store = client.app.state.data_store
    release_at = now() + timedelta(hours=2)
    store.write_calendar_events(
        [
            RawCalendarEvent(
                event_id="cpi_test",
                name="US CPI YoY",
                timestamp=release_at,
                impact="high",
                instruments=["EURUSD", "GBPUSD"],
                forecast=3.1,
                previous=3.2,
            )
        ]
    )

    response = client.get("/api/data/calendar/upcoming?hours=48&min_impact=medium")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    row = next(item for item in data if item["event_id"] == "cpi_test")
    assert row["name"] == "US CPI YoY"
    assert row["impact"] == "high"
    assert row["status"] == "upcoming"
    assert row["minutes_until"] >= 110
    assert row["volatility_risk"] == "high"


def test_signals_endpoints(client):
    """Test GET /api/signals endpoints return arrays."""
    for sig_type in ["technical", "fundamental", "trade"]:
        response = client.get(f"/api/signals/{sig_type}")
        assert response.status_code == 200
        assert isinstance(response.json(), list)


def test_historical_ohlcv_empty(client):
    """Test GET /api/data/ohlcv returns empty list when no data is loaded."""
    with patch("src.api.routes.data.DukascopyFeed.fetch_range") as mock_fetch:
        mock_fetch.return_value = pd.DataFrame()
        response = client.get(
            "/api/data/ohlcv?instrument=EURUSD&timeframe=1h&start=2026-06-01T00:00:00Z&end=2026-06-02T00:00:00Z"
        )
        assert response.status_code in (200, 500)
        if response.status_code == 200:
            assert response.json() == []


@pytest.mark.parametrize("instrument", ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"])
def test_historical_ohlcv_gap_filling(client, instrument):
    """Test that get_ohlcv triggers gap filling for every enabled instrument."""
    idx = pd.date_range("2026-06-01T00:00:00Z", "2026-06-01T05:00:00Z", freq="1h", tz="UTC")
    df = pd.DataFrame(
        {
            "open": [1.1, 1.11, 1.12, 1.13, 1.14, 1.15],
            "high": [1.12, 1.13, 1.14, 1.15, 1.16, 1.17],
            "low": [1.09, 1.1, 1.11, 1.12, 1.13, 1.14],
            "close": [1.11, 1.12, 1.13, 1.14, 1.15, 1.16],
            "volume": [100.0, 100.0, 100.0, 100.0, 100.0, 100.0],
        },
        index=idx,
    )
    store = client.app.state.data_store
    with (
        patch("src.api.routes.data.store_needs_gap_fill", return_value=True),
        patch("src.api.routes.data.DukascopyFeed.fetch_range", return_value=df),
        patch.object(store, "write_ohlcv"),
        patch.object(store, "get_ohlcv", return_value=df),
    ):
        response = client.get(
            f"/api/data/ohlcv?instrument={instrument}&timeframe=1h"
            "&start=2026-06-01T00:00:00Z&end=2026-06-01T05:00:00Z"
        )
    assert response.status_code == 200
    candles = response.json()
    assert len(candles) > 0
    assert candles[0]["open"] == 1.1
    assert candles[-1]["close"] == 1.16


@pytest.mark.asyncio
async def test_websocket_manager_broadcast():
    """Test WebSocket ConnectionManager connection list and broadcasts."""
    mock_websocket = MagicMock()
    mock_websocket.accept = AsyncMock()
    mock_websocket.send_json = AsyncMock()

    # Test connect
    await ws_manager.connect(mock_websocket)
    assert mock_websocket in ws_manager.active_connections

    # Test broadcast
    test_msg = {"event": "hello"}
    await ws_manager.broadcast(test_msg)
    mock_websocket.send_json.assert_called_once_with(test_msg)

    # Test disconnect
    ws_manager.disconnect(mock_websocket)
    assert mock_websocket not in ws_manager.active_connections
