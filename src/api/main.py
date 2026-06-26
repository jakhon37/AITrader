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

from src.api.middleware import RequestLoggingMiddleware
from src.api.routes import config, data, health, portfolio, signals, replay
from src.api.ws.handlers import setup_ws_bridge
from src.api.ws.manager import ws_manager
from src.core.bus import create_bus
from src.core.clock import set_clock, LiveClock
from src.core.config import load_config
from src.core.logging import get_logger
from src.core.contracts import Instrument, Timeframe
from src.data.feeds.dukascopy import DukascopyFeed
from src.data.pipeline.auto_refresh import DataRefreshWorker
from src.core.config import load_instruments
from src.core.instruments import get_enabled_instruments, get_scheduler_active_pairs
from src.data.scheduler import DataScheduler
from src.data.store import DataStore
from src.data.sources.news_fetcher import NewsFetcher
from src.data.sources.calendar import CalendarFetcher
from src.data.sources.fred import FredFetcher
from src.decision.engine import DecisionEngine
from src.execution.engine import ExecutionEngine
from src.technical.engine import TechnicalEngine
from src.fundamental.agent import FundamentalAgent
from src.notifier.service import NotifierService
from src.ops.monitor import OpsMonitor
import asyncio
import os

_log = get_logger("D10-WEBUI")


def _is_testing() -> bool:
    """Skip background loops during pytest (prevents TestClient lifespan hangs)."""
    return os.environ.get("AITRADER_TESTING") == "1"


class _TestSchedulerStub:
    """Minimal scheduler stand-in for API unit tests."""

    def get_live_status(self) -> dict[str, object]:
        return {
            "running": False,
            "active_pairs": [],
            "live_poll_adaptive": False,
        }

    def set_focused_pair(self, *_args: object, **_kwargs: object) -> bool:
        return False

    async def poll_pair_now(self, *_args: object, **_kwargs: object) -> None:
        return None

    def reset_last_emitted(self) -> None:
        return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for setting up bus subscriptions and store connections."""
    _log.info("webui_api_starting", testing=_is_testing())

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

    app.state.active_replay_session = None
    app.state.live_signal_pipeline_paused = False

    if _is_testing():
        engine = ExecutionEngine(config=app_config, bus=bus)
        app.state.engine = engine
        app.state.execution_store = engine.execution_store
        engine.start()
        app.state.scheduler = _TestSchedulerStub()
        app.state.dukascopy_feed = None
        app.state.refresh_worker = None
        _log.info("webui_api_started_test_mode")
        yield
        engine.stop()
        _log.info("webui_api_shutdown_test_mode")
        return

    # 4. Instantiate Execution Engine (runs in-process for paper trading)
    # Broker selection from config (currently falls back to SimBroker/mock until MT5/IBKR adapters are implemented)
    configured_broker = getattr(app_config.execution, 'broker', 'mock')
    engine = ExecutionEngine(config=app_config, bus=bus)
    app.state.engine = engine
    app.state.execution_store = engine.execution_store
    engine.start()
    await engine.seed_portfolio_state()
    _log.info("execution_engine_started", configured_broker=configured_broker, active="sim")

    # 5. Live signal spine: OHLCV_BAR → TechnicalSignal → TradeSignal
    technical_engine = TechnicalEngine(
        bus=bus,
        store=data_store,
        instruments_config=load_instruments(),
    )
    decision_engine = DecisionEngine(config=app_config, bus=bus)
    app.state.technical_engine = technical_engine
    app.state.decision_engine = decision_engine
    app.state.live_signal_pipeline_paused = False
    await technical_engine.start()
    await decision_engine.start()
    _log.info(
        "live_signal_spine_started",
        technical="D04",
        decision="D05",
    )

    # 6. Initialize Live Clock & DataScheduler
    clock = LiveClock()
    set_clock(clock)
    pipeline = app_config.data.pipeline
    dukascopy_feed = DukascopyFeed(
        live_m1_cache_ttl_sec=pipeline.live_m1_cache_ttl_sec,
        tick_enabled=pipeline.dukascopy_tick_enabled,
    )
    app.state.dukascopy_feed = dukascopy_feed

    enabled_instruments = get_enabled_instruments(app_config)
    bootstrap_pairs = get_scheduler_active_pairs(app_config)
    scheduler = DataScheduler(
        bus=bus,
        store=data_store,
        clock=clock,
        feed=dukascopy_feed,
        data_source=app_config.data.source,
        active_pairs=bootstrap_pairs,
        focused_poll_interval_sec=pipeline.live_poll_sec_focused,
        background_poll_interval_sec=pipeline.live_poll_sec_background,
        m1_poll_interval_sec=float(pipeline.live_poll_sec_m1),
        live_poll_adaptive=pipeline.live_poll_adaptive,
    )
    app.state.scheduler = scheduler

    # 7. Start the DataScheduler background task
    scheduler_task = asyncio.create_task(scheduler.run())
    app.state.scheduler_task = scheduler_task

    # 8. Automatic Dukascopy tail refresh (startup + hourly)
    refresh_worker = DataRefreshWorker(
        store=data_store,
        cfg=app_config,
        feed=dukascopy_feed,
        scheduler=scheduler,
    )
    app.state.refresh_worker = refresh_worker
    await refresh_worker.start()

    # 9. D02 + D03 Fundamental data pipeline (news + calendar + agent)
    # These were not started previously. Now wired as part of revised D03 plan.
    fund_cfg = getattr(app_config, "fundamental", None)
    news_poll = getattr(fund_cfg, "poll_interval_seconds", 600) if fund_cfg else 600

    news_fetcher = NewsFetcher(
        store=data_store,
        clock=clock,
        newsapi_key=os.environ.get("NEWSAPI_KEY"),
        poll_interval_seconds=news_poll,
    )
    app.state.news_fetcher = news_fetcher
    news_task = asyncio.create_task(news_fetcher.run())
    app.state.news_task = news_task

    calendar_fetcher = CalendarFetcher(
        store=data_store,
        bus=bus,
        clock=clock,
        poll_interval_seconds=3600,
    )
    app.state.calendar_fetcher = calendar_fetcher
    calendar_task = asyncio.create_task(calendar_fetcher.run())
    app.state.calendar_task = calendar_task

    # FundamentalAgent (D03) — uses pluggable backend from config (mock recommended on 16GB Intel Mac)
    fundamental_agent = FundamentalAgent(
        config=app_config,
        bus=bus,
        store=data_store,
    )
    app.state.fundamental_agent = fundamental_agent
    await fundamental_agent.start()
    _log.info("fundamental_pipeline_started", backend=getattr(fund_cfg, "sentiment_backend", "mock") if fund_cfg else "mock")

    # 10. Additional D02 APIs from .env (FRED macro data)
    if os.environ.get("FRED_API_KEY"):
        fred_fetcher = FredFetcher(
            data_base_dir=app_config.data.data_dir,
            clock=clock,
            api_key=os.environ.get("FRED_API_KEY"),
        )
        app.state.fred_fetcher = fred_fetcher
        fred_task = asyncio.create_task(fred_fetcher.run())
        app.state.fred_task = fred_task
        _log.info("fred_fetcher_started")
    else:
        _log.info("fred_fetcher_skipped_no_key")

    # 11. D07 Notifier (Telegram) if keys present
    if os.environ.get("TELEGRAM_BOT_TOKEN"):
        notifier = NotifierService(
            config=app_config,
            bus=bus,
            execution_store=engine.execution_store,
            fundamental_agent=fundamental_agent,
            data_store=data_store,
        )
        app.state.notifier = notifier
        notifier.seed_portfolio_cache(engine.execution_store.get_latest_portfolio())
        await notifier.start()
        bootstrap_signals = await fundamental_agent.publish_dev_bootstrap()
        if bootstrap_signals:
            notifier.seed_fundamental_cache(bootstrap_signals)
        _log.info("notifier_service_started")
    else:
        _log.info("notifier_skipped_no_telegram_key")

    # 12. D11 Ops monitor (data freshness, signal flow, audit, registry)
    ops_monitor = OpsMonitor(
        bus=bus,
        store=data_store,
        app_config=app_config,
        model_name=getattr(app_config.model, "model_type", None),
        scheduler=scheduler,
        notifier_active=bool(os.environ.get("TELEGRAM_BOT_TOKEN")),
        fundamental_active=True,
    )
    app.state.ops_monitor = ops_monitor
    await ops_monitor.start()
    _log.info("ops_monitor_started")

    _log.info("webui_api_started")
    yield

    # Cleanup / Shutdown
    if "ops_monitor" in app.state and app.state.ops_monitor:
        await app.state.ops_monitor.stop()
    await refresh_worker.stop()
    await technical_engine.stop()
    await decision_engine.stop()
    engine.stop()
    scheduler.stop()

    # D02/D03/D07 cleanup
    if "fundamental_agent" in app.state and app.state.fundamental_agent:
        await app.state.fundamental_agent.stop()
    if "news_fetcher" in app.state and app.state.news_fetcher:
        app.state.news_fetcher.stop()
    if "calendar_fetcher" in app.state and app.state.calendar_fetcher:
        app.state.calendar_fetcher.stop()
    if "fred_fetcher" in app.state and app.state.fred_fetcher:
        app.state.fred_fetcher.stop()
    if "notifier" in app.state and app.state.notifier:
        await app.state.notifier.stop()

    # Wait on tasks
    for task_name in ("scheduler_task", "news_task", "calendar_task", "fred_task"):
        task = getattr(app.state, task_name, None)
        if task:
            try:
                await asyncio.wait_for(task, timeout=5.0)
            except asyncio.TimeoutError:
                _log.warning(f"{task_name}_shutdown_timeout")
                task.cancel()
            except Exception as e:
                _log.exception(f"{task_name}_shutdown_error", error=str(e))

    _log.info("webui_api_shutdown")


# 2. App Initialization
app = FastAPI(
    title="AITrader Trading Terminal",
    description="Real-time professional AI algorithmic trading dashboard.",
    version="1.0.0",
    lifespan=lifespan,
)

# 3. Middleware
app.add_middleware(RequestLoggingMiddleware)
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
