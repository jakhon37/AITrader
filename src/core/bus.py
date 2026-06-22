"""Signal Bus — protocol + InProcessBus (asyncio) + factory.

Usage:
    from src.core.bus import create_bus
    bus = create_bus("memory")   # injected at startup from composition root

Never instantiate InProcessBus or RedisBus directly outside this file.

All divisions receive a Bus via dependency injection.
They call bus.publish(channel, payload) and bus.subscribe(channel, handler).
The RedisBus (for multi-process Phase 7) is a stub that raises NotImplementedError
until Phase 7 — all other divisions are written against the Bus Protocol only,
so the swap is transparent.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Awaitable, Callable, Protocol, runtime_checkable

from pydantic import BaseModel

from src.core.contracts import BusChannel
from src.core.exceptions import BusError
from src.core.logging import get_logger

_log = get_logger("D01-CORE")

Handler = Callable[[BaseModel], Awaitable[None]]


# ── Bus Protocol ──────────────────────────────────────────────────────────────

@runtime_checkable
class Bus(Protocol):
    """Bus interface.  All divisions depend only on this protocol."""

    async def publish(self, channel: BusChannel, payload: BaseModel) -> None:
        """Publish a payload to all subscribers of channel."""
        ...

    async def subscribe(self, channel: BusChannel, handler: Handler) -> None:
        """Register an async handler to receive messages on channel."""
        ...

    async def unsubscribe(self, channel: BusChannel, handler: Handler) -> None:
        """Remove a previously registered handler."""
        ...


# ── InProcessBus ──────────────────────────────────────────────────────────────

class InProcessBus:
    """Single-process bus backed by asyncio.  Zero external dependencies.

    All subscribers on a channel receive a copy of every published message.
    Subscriber ordering is insertion order (dict-backed set).
    Exceptions in handlers are logged and do NOT abort delivery to other subscribers.
    """

    def __init__(self, max_queue_size: int = 1000) -> None:
        # channel → ordered set of handlers
        self._subscribers: defaultdict[BusChannel, list[Handler]] = defaultdict(list)
        self._max_queue_size = max_queue_size

    async def publish(self, channel: BusChannel, payload: BaseModel) -> None:
        handlers = list(self._subscribers[channel])  # snapshot to avoid mutation during iteration
        if not handlers:
            return
        for handler in handlers:
            try:
                await handler(payload)
            except Exception as exc:  # noqa: BLE001
                _log.error(
                    "bus_handler_error",
                    channel=channel.value,
                    handler=getattr(handler, "__qualname__", repr(handler)),
                    error=str(exc),
                )

    async def subscribe(self, channel: BusChannel, handler: Handler) -> None:
        if handler not in self._subscribers[channel]:
            self._subscribers[channel].append(handler)

    async def unsubscribe(self, channel: BusChannel, handler: Handler) -> None:
        try:
            self._subscribers[channel].remove(handler)
        except ValueError:
            pass  # already unsubscribed — idempotent


# ── RedisBus stub ─────────────────────────────────────────────────────────────

class RedisBus:
    """Multi-process bus backed by Redis pub/sub.

    Available in Phase 7 (D11-OPS + Redis Bus milestone).
    All divisions are written against the Bus Protocol — the swap is transparent.
    """

    def __init__(self, url: str = "redis://localhost:6379") -> None:
        self._url = url

    async def publish(self, channel: BusChannel, payload: BaseModel) -> None:
        raise BusError(
            "RedisBus is not yet implemented. "
            "Set core.bus_backend='memory' for now (Phase 1–6)."
        )

    async def subscribe(self, channel: BusChannel, handler: Handler) -> None:
        raise BusError("RedisBus is not yet implemented.")

    async def unsubscribe(self, channel: BusChannel, handler: Handler) -> None:
        raise BusError("RedisBus is not yet implemented.")


# ── Factory ───────────────────────────────────────────────────────────────────

def create_bus(backend: str) -> Bus:
    """Create and return a Bus instance.

    Args:
        backend: "memory" for InProcessBus (default, Phase 1–6)
                 "redis"  for RedisBus (Phase 7+)

    Returns:
        A Bus-protocol-conformant instance.

    Raises:
        BusError: if backend is unknown.
    """
    if backend == "memory":
        return InProcessBus()
    if backend == "redis":
        return RedisBus()
    raise BusError(f"Unknown bus backend: {backend!r}. Choose 'memory' or 'redis'.")
