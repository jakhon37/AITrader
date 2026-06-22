"""Data feed for D08-BACKTEST.

Loads historical OHLCV data from DataStore across multiple timeframes,
sorts them chronologically by close time, and streams them while
advancing the ReplayClock to simulate real-time or fast-forward replay.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator

from src.core.clock import ReplayClock, get_clock
from src.core.contracts import Instrument, Timeframe, OHLCVBar
from src.data.store import DataStore
from src.technical.loader import timeframe_to_timedelta


class DataFeed:
    """Streams historical bars chronologically across multiple timeframes."""

    def __init__(
        self,
        store: DataStore,
        instrument: Instrument,
        timeframes: list[Timeframe],
        start: datetime,
        end: datetime,
        clock: ReplayClock | None = None,
    ) -> None:
        self.store = store
        self.instrument = instrument
        self.timeframes = timeframes
        self.start = start.astimezone(timezone.utc)
        self.end = end.astimezone(timezone.utc)
        # Use provided clock or get the active virtual clock
        self.clock = clock or get_clock()

    def _load_all_bars(self) -> list[tuple[datetime, OHLCVBar]]:
        """Load all bars in the range across all timeframes.

        Returns a list of tuples: (close_time, OHLCVBar).
        """
        all_bars = []

        for tf in self.timeframes:
            delta = timeframe_to_timedelta(tf)
            # Fetch data slightly earlier to capture any boundary bars
            fetch_start = self.start - delta
            
            try:
                df = self.store.get_ohlcv(self.instrument, tf, fetch_start, self.end)
            except Exception:
                # No data for this timeframe in store
                continue

            for ts, row in df.iterrows():
                # Ensure ts is timezone-aware
                if ts.tzinfo is None:
                    ts = ts.tz_localize("UTC")
                
                close_time = ts + delta
                
                # We only emit bars that close within the backtest window [start, end]
                if self.start <= close_time <= self.end:
                    bar = OHLCVBar(
                        signal_id=f"bar_{self.instrument.value}_{tf.value}_{ts.strftime('%Y%m%dT%H%M%S')}",
                        instrument=self.instrument,
                        timeframe=tf,
                        timestamp=ts,
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row["volume"]),
                        source="replay",
                    )
                    all_bars.append((close_time, bar))

        # Sort chronologically by close time.
        # If close times are identical, process lower timeframes first.
        # We can sort by close_time, and then by timeframe duration (ascending).
        all_bars.sort(key=lambda x: (x[0], timeframe_to_timedelta(x[1].timeframe)))
        return all_bars

    async def run(self, speed: float = 0.0) -> AsyncIterator[OHLCVBar]:
        """Stream bars chronologically.

        speed = 0.0: fast-forward (yield as fast as possible, no sleep)
        speed > 0.0: sleep proportional to the timeframe delta divided by speed
        """
        bars = self._load_all_bars()
        if not bars:
            return

        # Set clock to start time of the backtest
        self.clock.set_replay_time(self.start)

        last_emit_time = self.start

        for close_time, bar in bars:
            # Calculate sleep duration if speed > 0
            if speed > 0.0:
                time_delta = (close_time - last_emit_time).total_seconds()
                if time_delta > 0:
                    sleep_sec = time_delta / speed
                    # Limit maximum sleep to prevent hanging on weekend gaps
                    await asyncio.sleep(min(sleep_sec, 2.0))

            # Critical ordering: advance clock to bar's close time first,
            # then publish. In the same event loop tick with no awaits between.
            self.clock.set_replay_time(close_time)
            yield bar

            last_emit_time = close_time
