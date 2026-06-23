"""D02-DATA — Base settings and configurations for historical loaders."""

from __future__ import annotations

import os

from src.core.contracts import Instrument


class BaseHistoricalLoader:
    """Shared settings, instrument mappings, and configs for historical loaders."""

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
        environment: str = "practice",
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
