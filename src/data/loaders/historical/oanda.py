"""D02-DATA — OANDA REST API historical data fetcher mixin."""

from __future__ import annotations

import time
from datetime import datetime, timedelta

import pandas as pd
import requests

from src.core.contracts import Instrument, Timeframe
from src.core.exceptions import DataError
from src.core.logging import get_logger

_log = get_logger("D02-DATA")


class OANDAProvider:
    """Mixin providing historical fetching logic from OANDA."""

    def _fetch_oanda(
        self,
        instrument: Instrument,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """Fetch historical candles from OANDA REST API."""
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
