---
name: add-bus-subscriber
description: Use this skill when wiring any class or module to receive signals from the signal bus, adding a new handler for FundamentalSignal, TechnicalSignal, TradeSignal, or SystemEvent, or connecting a new division to the event system.
---

# add-bus-subscriber

Correctly wires a class to subscribe to one or more signal types on the SignalBus. This is the only safe pattern — deviations break the bus contract.

## The subscription pattern

```python
from signals.bus import get_bus
from signals.contracts import FundamentalSignal, TechnicalSignal, TradeSignal, SystemEvent

class MyComponent:
    def __init__(self, bus: SignalBus, clock: TradingClock, config: AppConfig):
        self.bus = bus
        self.clock = clock
        # Register handlers at construction time
        bus.subscribe(FundamentalSignal, self.on_fundamental)
        bus.subscribe(TechnicalSignal,   self.on_technical)
        bus.subscribe(TradeSignal,       self.on_trade)
        bus.subscribe(SystemEvent,       self.on_system)
    
    async def on_fundamental(self, signal: FundamentalSignal) -> None:
        # handle it
        ...
    
    async def on_technical(self, signal: TechnicalSignal) -> None:
        ...
    
    async def on_trade(self, signal: TradeSignal) -> None:
        ...
    
    async def on_system(self, event: SystemEvent) -> None:
        # filter by event.message or event.level before acting
        if event.message == "OHLCV_UPDATED":
            ...
        elif event.level == "CRITICAL":
            ...
```

## Rules — all mandatory

**1. Handlers must be async.** The bus awaits every handler. Sync functions will break the bus loop.

**2. Handlers must never raise.** Wrap handler body in try/except. A crashing handler stops delivery to subsequent subscribers.
```python
async def on_fundamental(self, signal: FundamentalSignal) -> None:
    try:
        await self._process(signal)
    except Exception as e:
        self.log.error("Handler failed", exc=e, signal_id=signal.signal_id)
```

**3. Never call `bus.subscribe()` outside `__init__`.** Subscriptions are permanent for the life of the object. Dynamic subscribe/unsubscribe is not supported.

**4. Never create the bus inside a component.** Always receive it via constructor injection. The bus is a singleton created at startup in `main.py`.

**5. Handlers must return quickly.** If processing is heavy (model inference, DB write), use `asyncio.to_thread()` or `asyncio.create_task()` — never block the bus loop.
```python
async def on_technical(self, signal: TechnicalSignal) -> None:
    # Heavy work — offload to thread pool
    await asyncio.to_thread(self._heavy_computation, signal)
```

**6. Never publish from inside a handler unless you understand the loop.** Publishing from a handler creates a recursive event — valid in some cases (decision engine publishes TradeSignal after receiving TechnicalSignal) but must be intentional.

## Wiring in main.py (startup)

```python
# main.py or application factory

from signals.bus import init_bus
from signals.clock import LiveClock
from notifications.notifier import NotificationService
from decision.engine import DecisionEngine

async def main():
    bus = init_bus()
    clock = LiveClock()
    config = AppConfig.from_env()
    
    # Construct components — subscriptions happen in __init__
    notification_svc = NotificationService(bus=bus, clock=clock, config=config)
    decision_engine  = DecisionEngine(bus=bus, clock=clock, config=config, ...)
    
    # Start the bus loop — must happen after all subscribers are registered
    await bus.run()
```

**Critical:** All components must be constructed before `bus.run()` is called. Signals published before `bus.run()` are queued and delivered once the loop starts.

## Subscribing only to specific instruments or levels

Filter inside the handler — the bus has no built-in filtering:

```python
async def on_fundamental(self, signal: FundamentalSignal) -> None:
    # Only handle XAUUSD
    if signal.instrument != Instrument.XAUUSD:
        return
    await self._process(signal)

async def on_system(self, event: SystemEvent) -> None:
    # Only handle WARNING and above
    if event.level not in ("WARNING", "ERROR", "CRITICAL"):
        return
    await self._alert(event)
```

## Integration test pattern

Every new subscriber needs an integration test:

```python
# tests/integration/test_execution.py
import asyncio
import pytest
from signals.bus import init_bus
from signals.contracts import FundamentalSignal, Direction, Instrument, EventType
from signals.utils import new_signal_id
from datetime import datetime

@pytest.mark.asyncio
async def test_my_component_receives_fundamental():
    bus = init_bus()
    clock = LiveClock()
    received = []
    
    class RecordingComponent:
        def __init__(self, bus):
            bus.subscribe(FundamentalSignal, self.on_fundamental)
        async def on_fundamental(self, signal):
            received.append(signal)
    
    component = RecordingComponent(bus)
    
    # Run bus briefly in background
    bus_task = asyncio.create_task(bus.run())
    
    # Publish a test signal
    await bus.publish(FundamentalSignal(
        signal_id=new_signal_id("FA", "EURUSD", datetime.utcnow()),
        timestamp=datetime.utcnow(),
        instrument=Instrument.EURUSD,
        direction=Direction.BULLISH,
        confidence=0.8,
        sentiment_score=0.4,
        event_type=EventType.ECONOMIC_DATA,
        event_summary="Test CPI beat",
        source_urls=["https://example.com"],
        decay_hours=4.0,
        raw_headlines=["CPI beats expectations"],
    ))
    
    await asyncio.sleep(0.05)   # let bus deliver
    bus_task.cancel()
    
    assert len(received) == 1
    assert received[0].instrument == Instrument.EURUSD
```

## Which divisions subscribe to what

| Division | Subscribes to |
|---|---|
| 3 (Technical) | `SystemEvent` (OHLCV_UPDATED, NEWS_BLACKOUT_START) |
| 5 (Decision) | `FundamentalSignal`, `TechnicalSignal`, `SystemEvent` |
| 6 (Execution) | `TradeSignal`, `SystemEvent` |
| 7 (Notifications) | `FundamentalSignal`, `TechnicalSignal`, `TradeSignal`, `SystemEvent` |
| 10 (API/WS) | all (broadcasts to WebSocket clients) |
| 11 (Monitoring) | `SystemEvent` (aggregates health) |
