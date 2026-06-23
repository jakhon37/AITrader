"""Main FastAPI Web UI Application Entry Point."""

from __future__ import annotations

import os
import sys
import subprocess

# Dynamic dependency booster
def bootstrap_dependencies():
    packages = []
    try:
        import fastapi
    except ImportError:
        packages.append("fastapi")
    
    try:
        import websockets
    except ImportError:
        packages.append("websockets")
        
    try:
        import uvicorn
    except ImportError:
        packages.append("uvicorn")
        
    if packages:
        print(f"Web UI dependencies missing inside container: {packages}. Installing...", flush=True)
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install"] + packages)
            print("Dependencies installed successfully!", flush=True)
        except Exception as e:
            print(f"Failed to install dependencies: {e}", file=sys.stderr, flush=True)
            sys.exit(1)

bootstrap_dependencies()

from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import config, data, health, portfolio, signals, replay
from src.api.ws.handlers import setup_ws_bridge
from src.api.ws.manager import ws_manager
from src.core.bus import create_bus
from src.core.clock import set_clock, LiveClock
from src.core.config import load_config
from src.core.logging import get_logger
from src.data.scheduler import DataScheduler
from src.data.store import DataStore
from src.execution.engine import ExecutionEngine
import asyncio

_log = get_logger("D10-WEBUI")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for setting up bus subscriptions and store connections."""
    _log.info("webui_api_starting")

    # 1. Load Configurations
    app_config = load_config()

    # 2. Instantiate DataStore
    data_store = DataStore(base_dir=app_config.data.data_dir)
    app.state.data_store = data_store
    app.state.app_config = app_config

    # 3. Create Bus & Setup WebSocket Bridge
    bus = create_bus(app_config.core.bus_backend)
    app.state.bus = bus
    await setup_ws_bridge(bus)

    # 4. Instantiate Execution Engine (runs in-process for paper trading)
    engine = ExecutionEngine(config=app_config, bus=bus)
    app.state.engine = engine
    engine.start()

    # 5. Initialize Live Clock & DataScheduler
    clock = LiveClock()
    set_clock(clock)
    scheduler = DataScheduler(
        bus=bus,
        store=data_store,
        clock=clock,
        active_pairs=[],
    )
    app.state.scheduler = scheduler

    # 6. Start the DataScheduler background task
    scheduler_task = asyncio.create_task(scheduler.run())
    app.state.scheduler_task = scheduler_task

    # Initialize active replay session placeholder
    app.state.active_replay_session = None

    _log.info("webui_api_started")
    yield

    # Cleanup / Shutdown
    engine.stop()
    scheduler.stop()
    try:
        await asyncio.wait_for(scheduler_task, timeout=5.0)
    except asyncio.TimeoutError:
        _log.warning("scheduler_shutdown_timeout")
        scheduler_task.cancel()
    except Exception as e:
        _log.exception("scheduler_shutdown_error", error=str(e))
    _log.info("webui_api_shutdown")


# 2. App Initialization
app = FastAPI(
    title="AITrader Trading Terminal",
    description="Real-time professional AI algorithmic trading dashboard.",
    version="1.0.0",
    lifespan=lifespan,
)

# 3. CORS Middleware Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Broad in dev mode, restrict in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 4. REST Routers Mount
app.include_router(data.router, prefix="/api")
app.include_router(signals.router, prefix="/api")
app.include_router(portfolio.router, prefix="/api")
app.include_router(config.router, prefix="/api")
app.include_router(health.router, prefix="/api")
app.include_router(replay.router, prefix="/api")


# 5. WebSocket Route Mount
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Accept real-time client socket connections."""
    await ws_manager.connect(websocket)
    try:
        while True:
            # Maintain connection alive, process incoming client pings/messages
            data = await websocket.receive_text()
            # Optional: parse client-sent WebSocket commands
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        _log.warning("websocket_error", error=str(e))
        ws_manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=True)
