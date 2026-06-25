"""Unit tests for D01-CORE.

Coverage target: 80% (critical path per MASTER.md coding standards).

Tests cover:
  - contracts.py  — round-trip serialize/deserialize every model; validation error cases
  - ids.py        — uniqueness, format
  - exceptions.py — hierarchy
  - clock.py      — LiveClock, ReplayClock (set/advance/reset), thread safety
  - bus.py        — InProcessBus publish→subscriber; multi-subscriber; channel isolation
  - config.py     — AppConfig loads from YAML; InstrumentConfig validates all fields
  - logging.py    — get_logger returns a usable logger
"""

from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.core.clock import (
    ClockMode,
    LiveClock,
    ReplayClock,
    get_clock,
    now,
    set_clock,
)
from src.core.bus import InProcessBus, create_bus
from src.core.contracts import (
    BusChannel,
    Direction,
    EconomicEvent,
    ExecutionMode,
    Instrument,
    MarketRegime,
    ModelArtifact,
    OHLCVBar,
    Order,
    OrderEvent,
    OrderSide,
    OrderStatus,
    PortfolioState,
    PositionSummary,
    PromotionStage,
    SignalStrength,
    SystemHealthEvent,
    HealthStatus,
    TechnicalSignal,
    Timeframe,
    TimeframeBias,
    TradeSignal,
    FundamentalSignal,
    FundamentalEventType,
    SignalSource,
)
from src.core.config import (
    AppConfig,
    CoreConfig,
    DataConfig,
    InstrumentConfig,
    SignalDecayConfig,
    load_config,
    load_instruments,
)
from src.core.exceptions import (
    AITraderError,
    BusError,
    ConfigError,
    DataError,
    ExecutionError,
    ReplayError,
    RiskViolation,
    SignalError,
)
from src.core.ids import new_signal_id
from src.core.logging import get_logger


# ── Helpers ───────────────────────────────────────────────────────────────────

UTC = timezone.utc


def utcnow() -> datetime:
    return datetime.now(UTC)


def make_ohlcv(**overrides: object) -> OHLCVBar:
    defaults = dict(
        signal_id=new_signal_id(),
        instrument=Instrument.EURUSD,
        timeframe=Timeframe.H1,
        timestamp=utcnow(),
        open=1.1000,
        high=1.1050,
        low=1.0980,
        close=1.1020,
        volume=1000.0,
        source="csv",
    )
    defaults.update(overrides)
    return OHLCVBar.model_validate(defaults)


# ══════════════════════════════════════════════════════════════════════════════
# ids.py
# ══════════════════════════════════════════════════════════════════════════════

class TestIds:
    def test_new_signal_id_is_string(self) -> None:
        sid = new_signal_id()
        assert isinstance(sid, str)

    def test_new_signal_id_is_uuid4_format(self) -> None:
        import uuid
        sid = new_signal_id()
        parsed = uuid.UUID(sid, version=4)
        assert str(parsed) == sid

    def test_new_signal_id_unique(self) -> None:
        ids = {new_signal_id() for _ in range(100)}
        assert len(ids) == 100


# ══════════════════════════════════════════════════════════════════════════════
# exceptions.py
# ══════════════════════════════════════════════════════════════════════════════

class TestExceptions:
    def test_hierarchy(self) -> None:
        assert issubclass(DataError, AITraderError)
        assert issubclass(SignalError, AITraderError)
        assert issubclass(ExecutionError, AITraderError)
        assert issubclass(RiskViolation, ExecutionError)
        assert issubclass(BusError, AITraderError)
        assert issubclass(ConfigError, AITraderError)
        assert issubclass(ReplayError, AITraderError)

    def test_raise_and_catch_as_root(self) -> None:
        with pytest.raises(AITraderError):
            raise DataError("fetch failed")

    def test_risk_violation_is_execution_error(self) -> None:
        with pytest.raises(ExecutionError):
            raise RiskViolation("drawdown exceeded")


# ══════════════════════════════════════════════════════════════════════════════
# clock.py
# ══════════════════════════════════════════════════════════════════════════════

class TestLiveClock:
    def test_now_is_utc(self) -> None:
        clock = LiveClock()
        ts = clock.now()
        assert ts.tzinfo is not None
        assert ts.utcoffset().total_seconds() == 0  # type: ignore[union-attr]

    def test_mode_is_live(self) -> None:
        assert LiveClock().mode() == ClockMode.LIVE

    def test_now_within_one_second_of_real_time(self) -> None:
        clock = LiveClock()
        before = datetime.now(UTC)
        ts = clock.now()
        after = datetime.now(UTC)
        assert before <= ts <= after


class TestReplayClock:
    def test_set_replay_time(self) -> None:
        clock = ReplayClock()
        target = datetime(2023, 1, 15, 10, 0, 0, tzinfo=UTC)
        clock.set_replay_time(target)
        assert clock.now() == target

    def test_advance(self) -> None:
        clock = ReplayClock(start=datetime(2023, 1, 1, tzinfo=UTC))
        clock.advance(timedelta(hours=1))
        assert clock.now() == datetime(2023, 1, 1, 1, 0, 0, tzinfo=UTC)

    def test_reset_to_live(self) -> None:
        clock = ReplayClock()
        clock.set_replay_time(datetime(2020, 1, 1, tzinfo=UTC))
        clock.reset_to_live()
        assert clock.mode() == ClockMode.LIVE
        # After reset, now() should be close to wall clock
        assert abs((clock.now() - datetime.now(UTC)).total_seconds()) < 2

    def test_mode_is_replay_after_set(self) -> None:
        clock = ReplayClock()
        clock.set_replay_time(datetime(2022, 6, 1, tzinfo=UTC))
        assert clock.mode() == ClockMode.REPLAY

    def test_requires_aware_datetime(self) -> None:
        clock = ReplayClock()
        with pytest.raises(ValueError, match="timezone-aware"):
            clock.set_replay_time(datetime(2022, 1, 1))  # naive — should raise

    def test_thread_safety(self) -> None:
        """Concurrent readers + one writer must never observe a torn read."""
        start = datetime(2023, 6, 1, tzinfo=UTC)
        clock = ReplayClock(start=start)
        errors: list[Exception] = []
        stop_flag = threading.Event()

        def reader() -> None:
            while not stop_flag.is_set():
                ts = clock.now()
                # The value must always be >= start — torn reads would produce nonsense
                if ts < start:
                    errors.append(AssertionError(f"Torn read: {ts}"))

        def writer() -> None:
            for i in range(500):
                clock.advance(timedelta(seconds=1))

        readers = [threading.Thread(target=reader) for _ in range(4)]
        for t in readers:
            t.start()

        writer_thread = threading.Thread(target=writer)
        writer_thread.start()
        writer_thread.join()

        stop_flag.set()
        for t in readers:
            t.join()

        assert not errors, f"Thread safety errors: {errors}"

    def test_advance_before_publish_ordering(self) -> None:
        """Advance must update time before any publish — confirmed by checking
        the clock reads the new time immediately after advance()."""
        clock = ReplayClock(start=datetime(2023, 1, 1, tzinfo=UTC))
        delta = timedelta(hours=4)
        clock.advance(delta)
        expected = datetime(2023, 1, 1, 4, 0, 0, tzinfo=UTC)
        assert clock.now() == expected


class TestGlobalNow:
    """Test the module-level now() accessor and set_clock()."""

    def test_now_returns_datetime(self) -> None:
        set_clock(LiveClock())
        ts = now()
        assert isinstance(ts, datetime)
        assert ts.tzinfo is not None

    def test_set_clock_replay(self) -> None:
        target = datetime(2024, 3, 20, 12, 0, 0, tzinfo=UTC)
        replay = ReplayClock(start=target)
        set_clock(replay)
        assert now() == target
        set_clock(LiveClock())  # restore

    def test_get_clock_returns_current(self) -> None:
        live = LiveClock()
        set_clock(live)
        assert get_clock() is live
        set_clock(LiveClock())  # restore


# ══════════════════════════════════════════════════════════════════════════════
# contracts.py
# ══════════════════════════════════════════════════════════════════════════════

class TestOHLCVBar:
    def test_round_trip(self) -> None:
        bar = make_ohlcv()
        dumped = bar.model_dump()
        restored = OHLCVBar.model_validate(dumped)
        assert restored == bar

    def test_json_round_trip(self) -> None:
        bar = make_ohlcv()
        json_str = bar.model_dump_json()
        restored = OHLCVBar.model_validate_json(json_str)
        assert restored.signal_id == bar.signal_id

    def test_invalid_instrument_raises(self) -> None:
        with pytest.raises(Exception):
            OHLCVBar.model_validate(
                dict(
                    signal_id=new_signal_id(),
                    instrument="INVALID",
                    timeframe="1h",
                    timestamp=utcnow().isoformat(),
                    open=1.1, high=1.2, low=1.0, close=1.15,
                    volume=100.0, source="csv",
                )
            )


class TestEconomicEvent:
    def test_round_trip(self) -> None:
        evt = EconomicEvent(
            signal_id=new_signal_id(),
            timestamp=utcnow(),
            name="US CPI YoY",
            impact="high",
            affected_pairs=[Instrument.EURUSD, Instrument.GBPUSD],
            actual=3.2,
            forecast=3.1,
            previous=3.0,
            surprise_pct=0.032,
        )
        dumped = evt.model_dump()
        assert EconomicEvent.model_validate(dumped) == evt

    def test_pre_release_none_actuals(self) -> None:
        """Before release, actual/forecast/previous may be None."""
        evt = EconomicEvent(
            signal_id=new_signal_id(),
            timestamp=utcnow(),
            name="FOMC Rate Decision",
            impact="high",
            affected_pairs=[Instrument.EURUSD],
        )
        assert evt.actual is None
        assert evt.surprise_pct is None


class TestTechnicalSignal:
    def _make(self) -> TechnicalSignal:
        bias = TimeframeBias(
            timeframe=Timeframe.H1,
            direction=Direction.LONG,
            confidence=0.75,
            regime=MarketRegime.TRENDING,
            indicators={"rsi": 55.0, "macd_hist": 0.002},
            support=1.0950,
            resistance=1.1100,
        )
        return TechnicalSignal(
            signal_id=new_signal_id(),
            instrument=Instrument.EURUSD,
            timestamp=utcnow(),
            valid_until=utcnow() + timedelta(hours=1),
            direction=Direction.LONG,
            confidence=0.8,
            strength=SignalStrength.STRONG,
            regime=MarketRegime.TRENDING,
            confluence_score=0.75,
            per_timeframe=[bias],
            primary_tf=Timeframe.H1,
            entry_price=1.1020,
            stop_loss=1.0980,
            take_profit=1.1100,
        )

    def test_round_trip(self) -> None:
        sig = self._make()
        assert TechnicalSignal.model_validate(sig.model_dump()) == sig

    def test_confidence_bounds(self) -> None:
        with pytest.raises(Exception):
            TechnicalSignal.model_validate(
                {**self._make().model_dump(), "confidence": 1.5}
            )


class TestModelArtifact:
    def test_round_trip(self) -> None:
        artifact = ModelArtifact(
            model_id=new_signal_id(),
            run_id=new_signal_id(),
            instrument=Instrument.EURUSD,
            model_type="lstm",
            promotion_stage=PromotionStage.STAGING,
            trained_at=utcnow(),
            promoted_at=utcnow(),
            cpcv_sharpe=1.4,
            cpcv_max_drawdown_pct=0.08,
            feature_set_version="v1.0",
            checkpoint_path="data/models/abc/checkpoint.pt",
            metadata_path="data/models/abc/metadata.json",
            previous_prod_model_id=None,
        )
        dumped = artifact.model_dump()
        assert ModelArtifact.model_validate(dumped).model_id == artifact.model_id


# ══════════════════════════════════════════════════════════════════════════════
# bus.py
# ══════════════════════════════════════════════════════════════════════════════

class TestInProcessBus:
    def test_publish_reaches_subscriber(self) -> None:
        received: list[OHLCVBar] = []

        async def handler(payload: object) -> None:
            received.append(payload)  # type: ignore[arg-type]

        async def run() -> None:
            bus = InProcessBus()
            await bus.subscribe(BusChannel.OHLCV_BAR, handler)
            bar = make_ohlcv()
            await bus.publish(BusChannel.OHLCV_BAR, bar)
            assert len(received) == 1
            assert received[0].signal_id == bar.signal_id

        asyncio.run(run())

    def test_multi_subscriber(self) -> None:
        counts: list[int] = [0, 0]

        async def h1(p: object) -> None:
            counts[0] += 1

        async def h2(p: object) -> None:
            counts[1] += 1

        async def run() -> None:
            bus = InProcessBus()
            await bus.subscribe(BusChannel.OHLCV_BAR, h1)
            await bus.subscribe(BusChannel.OHLCV_BAR, h2)
            await bus.publish(BusChannel.OHLCV_BAR, make_ohlcv())
            assert counts == [1, 1]

        asyncio.run(run())

    def test_channel_isolation(self) -> None:
        received: list[object] = []

        async def handler(p: object) -> None:
            received.append(p)

        async def run() -> None:
            bus = InProcessBus()
            await bus.subscribe(BusChannel.OHLCV_BAR, handler)
            # Publish to a DIFFERENT channel — handler should NOT receive it
            await bus.publish(BusChannel.TECHNICAL_SIGNAL, make_ohlcv())
            assert received == []

        asyncio.run(run())

    def test_unsubscribe(self) -> None:
        received: list[object] = []

        async def handler(p: object) -> None:
            received.append(p)

        async def run() -> None:
            bus = InProcessBus()
            await bus.subscribe(BusChannel.OHLCV_BAR, handler)
            await bus.unsubscribe(BusChannel.OHLCV_BAR, handler)
            await bus.publish(BusChannel.OHLCV_BAR, make_ohlcv())
            assert received == []

        asyncio.run(run())

    def test_handler_exception_does_not_drop_other_handlers(self) -> None:
        received: list[object] = []

        async def bad_handler(p: object) -> None:
            raise RuntimeError("deliberate failure")

        async def good_handler(p: object) -> None:
            received.append(p)

        async def run() -> None:
            bus = InProcessBus()
            await bus.subscribe(BusChannel.OHLCV_BAR, bad_handler)
            await bus.subscribe(BusChannel.OHLCV_BAR, good_handler)
            await bus.publish(BusChannel.OHLCV_BAR, make_ohlcv())
            assert len(received) == 1

        asyncio.run(run())

    def test_no_subscribers_is_noop(self) -> None:
        async def run() -> None:
            bus = InProcessBus()
            # Should not raise
            await bus.publish(BusChannel.OHLCV_BAR, make_ohlcv())

        asyncio.run(run())

    def test_create_bus_memory(self) -> None:
        bus = create_bus("memory")
        assert isinstance(bus, InProcessBus)

    def test_create_bus_unknown_raises(self) -> None:
        with pytest.raises(BusError):
            create_bus("kafka")


# ══════════════════════════════════════════════════════════════════════════════
# config.py
# ══════════════════════════════════════════════════════════════════════════════

class TestAppConfig:
    def test_defaults(self) -> None:
        cfg = AppConfig()
        assert cfg.env == "dev"
        assert cfg.core.bus_backend == "memory"
        assert cfg.core.execution_mode == ExecutionMode.PAPER

    def test_from_yaml(self, tmp_path: Path) -> None:
        yaml_content = """\
env: staging
data:
  symbols: ["EURUSD"]
  lookback_days: 30
"""
        p = tmp_path / "staging.yaml"
        p.write_text(yaml_content)
        cfg = AppConfig.from_yaml(p)
        assert cfg.env == "staging"
        assert cfg.data.lookback_days == 30

    def test_from_yaml_missing_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            AppConfig.from_yaml(tmp_path / "nonexistent.yaml")

    def test_from_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        yaml_content = "env: dev\n"
        (tmp_path / "dev.yaml").write_text(yaml_content)
        monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("ENV", "dev")
        cfg = AppConfig.from_env()
        assert cfg.env == "dev"

    def test_get_symbols_normalized(self) -> None:
        cfg = AppConfig(
            data=DataConfig(symbols=["EUR_USD", "GBP_USD", "USD_JPY", "XAUUSD"])
        )
        assert cfg.get_symbols_normalized() == ["eurusd", "gbpusd", "usdjpy", "xauusd"]

    def test_invalid_env_raises(self) -> None:
        with pytest.raises(Exception):
            AppConfig.model_validate({"env": "production"})  # only dev|staging|prod allowed


class TestInstrumentConfig:
    def test_valid(self) -> None:
        cfg = InstrumentConfig(
            pip_size=0.0001,
            lot_size=100000,
            session_hours={"open": "22:00", "close": "22:00"},
            active_timeframes=[Timeframe.H1, Timeframe.H4],
            primary_timeframe=Timeframe.H1,
        )
        assert cfg.fundamental_weight == 0.3
        assert cfg.news_halt_minutes == 30

    def test_signal_decay_defaults(self) -> None:
        cfg = InstrumentConfig(
            pip_size=0.01,
            lot_size=100,
            session_hours={"open": "22:00", "close": "22:00"},
            active_timeframes=[Timeframe.H1],
            primary_timeframe=Timeframe.H1,
        )
        assert cfg.signal_decay.central_bank == 48.0
        assert cfg.signal_decay.geopolitical == 6.0


class TestLoadInstruments:
    def test_loads_all_four(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import os
        # Point CONFIG_DIR to the real project config directory
        config_dir = Path(__file__).parents[2] / "config"
        monkeypatch.setenv("CONFIG_DIR", str(config_dir))
        instruments = load_instruments()
        assert Instrument.EURUSD in instruments
        assert Instrument.GBPUSD in instruments
        assert Instrument.USDJPY in instruments
        assert Instrument.XAUUSD in instruments

    def test_missing_file_raises_config_error(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError):
            load_instruments(tmp_path / "no_such_file.yaml")


# ══════════════════════════════════════════════════════════════════════════════
# logging.py
# ══════════════════════════════════════════════════════════════════════════════

class TestLogging:
    def test_get_logger_returns_something(self) -> None:
        log = get_logger("D01-CORE")
        assert log is not None

    def test_logger_has_info_method(self) -> None:
        log = get_logger("D01-CORE")
        assert callable(getattr(log, "info", None))

    def test_logger_bind(self) -> None:
        log = get_logger("D01-CORE")
        bound = log.bind(signal_id="abc", instrument="EURUSD")
        assert bound is not None
