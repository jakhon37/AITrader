"""D02-DATA — Loader for fetching historical backfill data from OANDA or yfinance."""

from __future__ import annotations

import os
from datetime import datetime
import pandas as pd
import yfinance as yf

from src.core.contracts import Instrument, Timeframe
from src.core.exceptions import DataError
from src.core.logging import get_logger

_log = get_logger("D02-DATA")


class OANDAHistoricalLoader:
    """Historical data loader for one-time backfills.

    Supports OANDA REST API backfilling if credentials are provided,
    and falls back to yfinance (up to 60-day limit) otherwise.
    """

    # Mapping internal Instrument to OANDA currency pair string
    OANDA_INSTRUMENTS = {
        Instrument.EURUSD: "EUR_USD",
        Instrument.GBPUSD: "GBP_USD",
        Instrument.USDJPY: "USD_JPY",
        Instrument.XAUUSD: "XAU_USD",
    }

    # Mapping internal Instrument to yfinance ticker
    YFINANCE_TICKERS = {
        Instrument.EURUSD: "EURUSD=X",
        Instrument.GBPUSD: "GBPUSD=X",
        Instrument.USDJPY: "USDJPY=X",
        Instrument.XAUUSD: "GC=F",
    }

    def __init__(
        self,
        api_token: str | None = None,
        account_id: str | None = None,
        environment: str = "practice"
    ) -> None:
        self.api_token = (
            api_token 
            or os.environ.get("OANDA_API_TOKEN") 
            or os.environ.get("BROKER_API_KEY")
        )
        self.account_id = (
            account_id 
            or os.environ.get("OANDA_ACCOUNT_ID") 
            or os.environ.get("BROKER_ACCOUNT_ID")
        )
        self.environment = environment

    def fetch_history(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """Fetch historical OHLCV data for backfill.

        Order of priority:
        1. OANDA API (main - deep lookback, requires credentials)
        2. Dukascopy (fallback - deep lookback, automatic, requires no credentials)
        3. yfinance (fallback - lookback-capped, requires no credentials)
        """
        # 1. Try OANDA if credentials are present
        if self.api_token and self.account_id:
            try:
                return self._fetch_oanda(instrument, timeframe, start, end)
            except Exception as e:
                msg = f"⚠️ WARNING: OANDA fetch failed for {instrument.value} ({timeframe.value}): {e}. Trying Dukascopy fallback..."
                print(msg)
                _log.warning(
                    "oanda_fetch_failed_trying_dukascopy",
                    instrument=instrument.value,
                    error=str(e),
                )
        else:
            msg = f"ℹ️ INFO: OANDA credentials not set. Trying Dukascopy fallback for {instrument.value} ({timeframe.value})..."
            print(msg)

        # 2. Try Dukascopy (automatic deep history)
        try:
            return self._fetch_dukascopy(instrument, timeframe, start, end)
        except Exception as e:
            msg = f"⚠️ WARNING: Dukascopy fetch failed for {instrument.value} ({timeframe.value}): {e}. Trying yfinance fallback..."
            print(msg)
            _log.warning(
                "dukascopy_fetch_failed_trying_yfinance",
                instrument=instrument.value,
                error=str(e),
            )

        # 3. Try yfinance (capped fallback)
        msg = f"ℹ️ INFO: Falling back to yfinance for {instrument.value} ({timeframe.value}). Lookback limits will apply."
        print(msg)
        return self._fetch_yfinance(instrument, timeframe, start, end)

    def _fetch_dukascopy(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """Fetch daily 1-minute candles from Dukascopy datafeed and resample them."""
        import requests
        import lzma
        import struct
        import time
        from datetime import timezone, timedelta

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
        import random

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

    def _fetch_oanda(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """Fetch historical candles from OANDA REST API."""
        import requests

        oanda_pair = self.OANDA_INSTRUMENTS.get(instrument)
        if not oanda_pair:
            raise DataError(f"No OANDA mapping for {instrument.value}")

        # Map Timeframe to OANDA granularity
        _GRANULARITY_MAP = {
            Timeframe.M1: "M1",
            Timeframe.M5: "M5",
            Timeframe.M15: "M15",
            Timeframe.M30: "M30",
            Timeframe.H1: "H1",
            Timeframe.H4: "H4",
            Timeframe.D1: "D",
        }
        granularity = _GRANULARITY_MAP.get(timeframe)
        if not granularity:
            raise DataError(f"Granularity mapping not found for {timeframe.value}")

        domain = (
            "api-fxpractice.oanda.com"
            if self.environment == "practice"
            else "api-fxtrade.oanda.com"
        )
        url = f"https://{domain}/v3/instruments/{oanda_pair}/candles"
        
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }
        
        from datetime import timedelta
        import time

        _CHUNK_DELTAS = {
            Timeframe.M1: timedelta(days=3),
            Timeframe.M5: timedelta(days=15),
            Timeframe.M15: timedelta(days=45),
            Timeframe.M30: timedelta(days=90),
            Timeframe.H1: timedelta(days=180),
            Timeframe.H4: timedelta(days=700),
            Timeframe.D1: timedelta(days=3650),
        }
        chunk_delta = _CHUNK_DELTAS.get(timeframe, timedelta(days=30))

        rows = []
        current_start = start

        while current_start < end:
            current_end = min(current_start + chunk_delta, end)
            if current_start >= current_end:
                break

            params = {
                "from": current_start.isoformat(),
                "to": current_end.isoformat(),
                "granularity": granularity,
                "price": "M",  # Midpoint
            }

            _log.info(
                "oanda_requesting_candles_chunk",
                pair=oanda_pair,
                granularity=granularity,
                chunk_start=current_start.isoformat(),
                chunk_end=current_end.isoformat(),
            )

            res = requests.get(url, headers=headers, params=params, timeout=15)
            if not res.ok:
                raise DataError(f"OANDA API returned error {res.status_code}: {res.text}")

            payload = res.json()
            candles = payload.get("candles", [])
            
            chunk_rows_count = 0
            for c in candles:
                if not c.get("complete"):
                    continue
                mid = c["mid"]
                dt = pd.to_datetime(c["time"])
                rows.append({
                    "timestamp": dt,
                    "open": float(mid["o"]),
                    "high": float(mid["h"]),
                    "low": float(mid["l"]),
                    "close": float(mid["c"]),
                    "volume": float(c["volume"]),
                })
                chunk_rows_count += 1
                
            _log.info(
                "oanda_chunk_received",
                count=chunk_rows_count
            )

            current_start = current_end
            if current_start < end:
                time.sleep(0.3)

        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.set_index("timestamp").sort_index()
            df = df[~df.index.duplicated(keep="last")]
            df.index = df.index.tz_convert("UTC")
        return df

    def _fetch_yfinance(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """Fetch historical candles from yfinance (fallback)."""
        ticker_sym = self.YFINANCE_TICKERS.get(instrument)
        if not ticker_sym:
            raise DataError(f"No yfinance ticker mapping for {instrument.value}")

        _TF_MAP = {
            Timeframe.M1: "1m",
            Timeframe.M5: "5m",
            Timeframe.M15: "15m",
            Timeframe.M30: "30m",
            Timeframe.H1: "1h",
            Timeframe.H4: "1h",  # We will resample this if requested
            Timeframe.D1: "1d",
            Timeframe.W1: "1wk",
        }
        yf_interval = _TF_MAP.get(timeframe, "1d")

        _log.info(
            "yfinance_backfill_fetching",
            ticker=ticker_sym,
            interval=yf_interval,
            start=start.date().isoformat(),
            end=end.date().isoformat(),
        )

        # yfinance download
        df = yf.download(
            ticker_sym,
            start=start,
            end=end,
            interval=yf_interval,
            progress=False,
        )

        if df.empty:
            return pd.DataFrame()

        # Format columns
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [str(c).lower() for c in df.columns]

        required = ["open", "high", "low", "close", "volume"]
        df = df[[c for c in required if c in df.columns]].dropna(subset=["open", "high", "low", "close"])

        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        else:
            df.index = df.index.tz_convert("UTC")

        # Custom Resampling H1 to H4 if timeframe is H4
        if timeframe == Timeframe.H4 and yf_interval == "1h":
            from src.data.resample import resample_4h
            df = resample_4h(df)

        return df
