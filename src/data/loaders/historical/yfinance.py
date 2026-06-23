"""D02-DATA — Yahoo Finance historical data fetcher mixin."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import yfinance as yf

from src.core.contracts import Instrument, Timeframe
from src.core.exceptions import DataError
from src.core.logging import get_logger

_log = get_logger("D02-DATA")


class YFinanceProvider:
    """Mixin providing historical fetching logic from yfinance as a fallback."""

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
