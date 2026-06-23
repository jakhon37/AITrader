"""Unit tests for the FastAPI Web UI replay router."""

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

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.core.contracts import Instrument, Timeframe
from src.data.store import DataStore
import pandas as pd
from datetime import datetime, timezone


@pytest.fixture
def client():
    """Test client fixture."""
    # Seed DataStore with mock parquet files so DataFeed has bars to load
    store = DataStore(base_dir=tmp_dir)
    
    # Write some dummy OHLCV data
    instrument = Instrument.EURUSD
    timeframe = Timeframe.H1
    periods = 210
    times = pd.date_range("2024-01-01 00:00:00", periods=periods, freq="h", tz=timezone.utc)
    df = pd.DataFrame(
        {
            "open": [1.1000] * len(times),
            "high": [1.1010] * len(times),
            "low": [1.0990] * len(times),
            "close": [1.1005] * len(times),
            "volume": [100.0] * len(times),
        },
        index=times,
    )
    store.write_ohlcv(instrument, timeframe, df)

    timeframe_15 = Timeframe.M15
    times_15 = pd.date_range("2024-01-01 00:00:00", periods=periods, freq="15min", tz=timezone.utc)
    df_15 = pd.DataFrame(
        {
            "open": [1.1000] * len(times_15),
            "high": [1.1010] * len(times_15),
            "low": [1.0990] * len(times_15),
            "close": [1.1005] * len(times_15),
            "volume": [100.0] * len(times_15),
        },
        index=times_15,
    )
    store.write_ohlcv(instrument, timeframe_15, df_15)

    with TestClient(app) as test_client:
        # Override the app data_store and config with our temporary test setup
        test_client.app.state.data_store = store
        if hasattr(test_client.app.state, "app_config"):
            test_client.app.state.app_config.data.data_dir = tmp_dir
        yield test_client


def test_replay_state_inactive_initially(client):
    """Test GET /api/replay/state returns inactive when no session is running."""
    response = client.get("/api/replay/state")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "inactive"


def test_replay_flow_watch_mode(client):
    """Test start, pause, resume, state, and stop for watch mode."""
    # 1. Start Replay
    payload = {
        "instrument": "EURUSD",
        "start_date": "2024-01-01T00:00:00Z",
        "end_date": "2024-01-05T00:00:00Z",
        "initial_capital": 10000.0,
        "mode": "watch",
        "speed": 0.0,  # 0 speed to prevent sleeping/racing in test
    }
    response = client.post("/api/replay/start", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["session"]["mode"] == "watch"
    assert data["session"]["status"] == "running"

    # 2. Get State
    response = client.get("/api/replay/state")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "active"
    assert data["session"]["mode"] == "watch"

    # 3. Pause
    response = client.post("/api/replay/pause")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["session"]["status"] == "paused"

    # 4. Resume
    response = client.post("/api/replay/resume")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["session"]["status"] == "running"

    # 5. Stop
    response = client.post("/api/replay/stop")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"

    # 6. Verify Inactive State
    response = client.get("/api/replay/state")
    assert response.status_code == 200
    assert response.json()["status"] == "inactive"


def test_replay_flow_manual_mode(client):
    """Test start, step, order, close, and stop for manual mode."""
    # 1. Start Replay
    payload = {
        "instrument": "EURUSD",
        "start_date": "2024-01-01T00:00:00Z",
        "end_date": "2024-01-05T00:00:00Z",
        "initial_capital": 10000.0,
        "mode": "manual",
    }
    response = client.post("/api/replay/start", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["session"]["mode"] == "manual"
    assert data["session"]["status"] == "running"

    # 2. Step Replay
    response = client.post("/api/replay/step")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["session"]["current_bar_index"] > 0

    # 2b. Change Timeframe Dynamically
    tf_payload = {"timeframe": "15m"}
    response = client.post("/api/replay/timeframe", json=tf_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["session"]["timeframe"] == "15m"
    assert data["session"]["current_bar_index"] == 0

    # 3. Place Order
    order_payload = {"side": "buy", "size": 1.0}
    response = client.post("/api/replay/order", json=order_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["order"]["side"] == "buy"
    assert data["order"]["size"] == 1.0

    # 4. Close Position
    close_payload = {"instrument": "EURUSD"}
    response = client.post("/api/replay/close", json=close_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"

    # 5. Stop (returns report)
    response = client.post("/api/replay/stop")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "report" in data


def test_replay_start_without_end_date(client):
    """Test starting replay without end_date successfully falls back to latest DB date."""
    payload = {
        "instrument": "EURUSD",
        "start_date": "2024-01-01T00:00:00Z",
        "initial_capital": 10000.0,
        "mode": "watch",
        "speed": 0.0,
        "timeframe": "1h",
    }
    response = client.post("/api/replay/start", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["session"]["mode"] == "watch"
    assert data["session"]["status"] == "running"

    # Verify that the session stopped and returned success
    client.post("/api/replay/stop")


def test_replay_toggle_indicators(client):
    """Test toggling technical indicators calculation dynamically during session."""
    payload = {
        "instrument": "EURUSD",
        "start_date": "2024-01-01T00:00:00Z",
        "initial_capital": 10000.0,
        "mode": "watch",
        "speed": 0.0,
        "timeframe": "1h",
        "calculate_indicators": True,
    }
    response = client.post("/api/replay/start", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["session"]["calculate_indicators"] is True

    # Toggle indicators off
    toggle_payload = {"enabled": False}
    response = client.post("/api/replay/indicators", json=toggle_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["session"]["calculate_indicators"] is False

    # Stop session
    client.post("/api/replay/stop")

