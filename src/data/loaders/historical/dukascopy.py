"""D02-DATA — Dukascopy historical data fetcher mixin."""

from __future__ import annotations

import random
import time
from datetime import datetime, timedelta

import pandas as pd

from src.core.contracts import Instrument, Timeframe
from src.core.exceptions import DataError
from src.core.logging import get_logger

_log = get_logger("D02-DATA")


class DukascopyProvider:
    """Mixin providing historical binary candle fetching and parsing logic from Dukascopy."""

    def _fetch_dukascopy(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """Fetch daily 1-minute candles from Dukascopy datafeed and resample them."""
        import lzma
        import struct
        from datetime import timezone
        
        import requests

        symbol_map = {
            Instrument.EURUSD: "EURUSD",
            Instrument.GBPUSD: "GBPUSD",
            Instrument.USDJPY: "USDJPY",
            Instrument.XAUUSD: "XAUUSD",
        }
        symbol = symbol_map.get(instrument)
        if not symbol:
            raise DataError(f"No Dukascopy mapping for {instrument.value}")

        divisors = {
            "EURUSD": 100000.0,
            "GBPUSD": 100000.0,
            "USDJPY": 1000.0,
            "XAUUSD": 1000.0,
        }
        divisor = divisors.get(symbol, 100000.0)

        current_date = start.date()
        end_date = end.date()

        all_dfs = []
        fmt = ">5If"
        record_size = struct.calcsize(fmt)

        _log.info(
            "dukascopy_fetch_started",
            instrument=instrument.value,
            start=start.isoformat(),
            end=end.isoformat(),
        )

        requests_count = 0

        while current_date <= end_date:
            year = current_date.year
            month = current_date.month - 1  # 0-based month
            day = current_date.day

            url = (
                f"https://datafeed.dukascopy.com/datafeed/"
                f"{symbol}/{year}/{month:02d}/{day:02d}/BID_candles_min_1.bi5"
            )

            # Retry logic with progressive backoff for rate limits or connection glitches
            retries = 3
            res = None
            for attempt in range(retries):
                try:
                    res = requests.get(url, timeout=10)
                    if res.status_code in (403, 429):
                        # Exponential backoff sleep: 60s, 120s, 300s
                        backoff_sleep = [60, 120, 300][attempt]
                        msg = f"⚠️ Rate limit hit (HTTP {res.status_code}) on {current_date}. Retrying in {backoff_sleep} seconds (Attempt {attempt+1}/{retries})...."
                        print(msg)
                        time.sleep(backoff_sleep)
                        continue
                    break
                except Exception as e:
                    if attempt == retries - 1:
                        raise e
                    print(f"⚠️ Connection error on {current_date}: {e}. Retrying in 10 seconds...")
                    time.sleep(10)

            if res is None:
                current_date += timedelta(days=1)
                continue

            try:
                if res.status_code == 200:
                    decompressed = lzma.decompress(res.content)
                    num_records = len(decompressed) // record_size

                    records = []
                    for i in range(num_records):
                        offset = i * record_size
                        chunk = decompressed[offset:offset+record_size]
                        unpacked = struct.unpack(fmt, chunk)
                        records.append(unpacked)

                    if records:
                        day_df = pd.DataFrame(
                            records,
                            columns=["time_sec", "open", "close", "low", "high", "volume"]
                        )

                        # Generate datetime timestamps (UTC)
                        base_dt = datetime(year, month + 1, day, tzinfo=timezone.utc)
                        day_df["timestamp"] = base_dt + pd.to_timedelta(day_df["time_sec"], unit="s")

                        # Scale prices
                        for col in ["open", "high", "low", "close"]:
                            day_df[col] = day_df[col] / divisor

                        # Correct high/low bounds
                        day_df["high"] = day_df[["open", "close", "low", "high"]].max(axis=1)
                        day_df["low"] = day_df[["open", "close", "low", "high"]].min(axis=1)

                        day_df = day_df.set_index("timestamp")
                        all_dfs.append(day_df[["open", "high", "low", "close", "volume"]])

                elif res.status_code == 404:
                    # Weekend or holiday, skip silently
                    pass
                else:
                    _log.warning(
                        "dukascopy_download_non_200",
                        url=url,
                        status=res.status_code
                    )
            except Exception as e:
                _log.warning(
                    "dukascopy_download_error",
                    url=url,
                    error=str(e)
                )

            current_date += timedelta(days=1)
            requests_count += 1
            
            if current_date <= end_date:
                # Proactive cooldown every 50 requests
                if requests_count % 50 == 0:
                    print(f"☕ Cooldown: Fetched {requests_count} days. Sleeping for 10 seconds...")
                    time.sleep(10)
                else:
                    # Pacing sleep with random jitter (average 0.6 seconds)
                    pacing_delay = 0.4 + random.uniform(0.0, 0.4)
                    time.sleep(pacing_delay)

        if not all_dfs:
            raise DataError(f"No Dukascopy data found for {instrument.value} in range.")

        df = pd.concat(all_dfs).sort_index()
        df = df[~df.index.duplicated(keep="last")]

        # Resample to the requested timeframe if it is not M1
        if timeframe != Timeframe.M1:
            _TF_MAP = {
                Timeframe.M5: "5min",
                Timeframe.M15: "15min",
                Timeframe.M30: "30min",
                Timeframe.H1: "1h",
                Timeframe.H4: "4h",
                Timeframe.D1: "1d",
                Timeframe.W1: "1wk",
            }
            rule = _TF_MAP.get(timeframe)
            if rule:
                resampled = pd.DataFrame()
                resampled["open"] = df["open"].resample(rule).first()
                resampled["high"] = df["high"].resample(rule).max()
                resampled["low"] = df["low"].resample(rule).min()
                resampled["close"] = df["close"].resample(rule).last()
                resampled["volume"] = df["volume"].resample(rule).sum()
                df = resampled.dropna()

        # Slice to start and end
        df = df.loc[start:end]
        return df
