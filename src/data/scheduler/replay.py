"""Replay-mode tick — emit bars from store on virtual clock boundaries."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.core.candle import candle_open_time
from src.core.contracts import BusChannel
from src.core.exceptions import DataError
from src.core.logging import get_logger
from src.data.scheduler.store_ops import load_bar_from_store

if TYPE_CHECKING:
    from src.data.scheduler.core import DataScheduler

_log = get_logger("D02-DATA")


class ReplaySchedulerMixin:
    """Virtual-clock replay mixed into DataScheduler."""

    async def tick(self: DataScheduler) -> None:
        """Check the virtual clock and emit any bars whose close time has passed."""
        now = self._clock.now()
        for instrument, timeframe in self._active_pairs:
            candle_open = candle_open_time(now, timeframe)
            last = self._last_emitted.get((instrument, timeframe))
            if last is not None and candle_open <= last:
                continue

            try:
                bar = load_bar_from_store(
                    self._store, instrument, timeframe, candle_open
                )
            except DataError as exc:
                _log.warning(
                    "scheduler_replay_bar_missing",
                    instrument=instrument.value,
                    timeframe=timeframe.value,
                    candle_open=str(candle_open),
                    error=str(exc),
                )
                continue

            await self._bus.publish(BusChannel.OHLCV_BAR, bar)
            self._last_emitted[(instrument, timeframe)] = bar.timestamp

            _log.debug(
                "ohlcv_bar_replayed",
                instrument=instrument.value,
                timeframe=timeframe.value,
                bar_ts=str(bar.timestamp),
                close=bar.close,
            )