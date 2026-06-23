"""D02-DATA — Historical Backfill Data Loader package."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from src.core.contracts import Instrument, Timeframe
from src.core.logging import get_logger
from src.data.loaders.historical._base import BaseHistoricalLoader
from src.data.loaders.historical.oanda import OANDAProvider
from src.data.loaders.historical.dukascopy import DukascopyProvider
from src.data.loaders.historical.yfinance import YFinanceProvider

_log = get_logger("D02-DATA")


class OANDAHistoricalLoader(
    OANDAProvider,
    DukascopyProvider,
    YFinanceProvider,
    BaseHistoricalLoader,
):
    """Historical data loader for one-time backfills.

    Supports OANDA REST API backfilling if credentials are provided,
    and falls back to Dukascopy or yfinance otherwise.
    """

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


__all__ = ["OANDAHistoricalLoader"]
