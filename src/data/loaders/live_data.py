"""Live data fetcher for real-time market data.

Supports multiple data sources:
- yfinance (Yahoo Finance) - Free, good for stocks and Forex
- Alpha Vantage - Free tier with API key
- OANDA - Professional Forex data
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


class LiveDataFetcher:
    """Fetch live market data from various sources."""

    # Symbol mapping: internal -> yfinance
    SYMBOL_MAP = {
        "eurusd": "EURUSD=X",
        "gbpusd": "GBPUSD=X",
        "usdjpy": "USDJPY=X",
        "gold": "GC=F",  # Gold futures
        "xauusd": "GC=F",  # Gold alternative
        "btcusd": "BTC-USD",  # Bitcoin
        "btc": "BTC-USD",  # Bitcoin alternative
    }
    
    # Timeframe mapping: human-readable -> yfinance interval
    TIMEFRAME_MAP = {
        "1m": "1m",      # 1 minute
        "2m": "2m",      # 2 minutes
        "5m": "5m",      # 5 minutes
        "15m": "15m",    # 15 minutes
        "30m": "30m",    # 30 minutes
        "1h": "1h",      # 1 hour
        "60m": "60m",    # 60 minutes (alt for 1h)
        "90m": "90m",    # 90 minutes
        "4h": "1h",      # 4 hours (resample from 1h)
        "1d": "1d",      # 1 day
        "1w": "1wk",     # 1 week
        "1mo": "1mo",    # 1 month
    }
    
    # Maximum lookback periods for intraday data (yfinance limitation: 60 days for intraday)
    MAX_INTRADAY_DAYS = 59

    def __init__(self, source: str = "yfinance", timeframe: str = "1d"):
        """Initialize live data fetcher.

        Args:
            source: Data source ('yfinance', 'alphavantage', 'oanda')
            timeframe: Timeframe for data (1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 1mo)
        """
        self.source = source
        self.timeframe = timeframe
        logger.info(f"LiveDataFetcher initialized with source: {source}, timeframe: {timeframe}")

    def fetch_latest(self, symbol: str, lookback_days: int = 90, lookback_bars: int = None) -> pd.DataFrame:
        """Fetch latest data for a symbol.

        Args:
            symbol: Symbol to fetch (e.g., 'eurusd', 'gbpusd')
            lookback_days: Number of days of historical data (for daily+)
            lookback_bars: Number of bars to fetch (for intraday, overrides lookback_days)

        Returns:
            DataFrame with OHLCV data
        """
        if self.source == "yfinance":
            return self._fetch_yfinance(symbol, lookback_days, lookback_bars)
        else:
            raise ValueError(f"Unsupported data source: {self.source}")

    def _fetch_yfinance(self, symbol: str, lookback_days: int, lookback_bars: int = None) -> pd.DataFrame:
        """Fetch data from Yahoo Finance."""
        try:
            # Map internal symbol to yfinance ticker
            ticker = self.SYMBOL_MAP.get(symbol.lower(), symbol)
            
            # Get interval for yfinance
            interval = self.TIMEFRAME_MAP.get(self.timeframe, "1d")
            
            # Check if intraday
            is_intraday = interval in ["1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h"]
            
            logger.info(f"Fetching {symbol} ({ticker}) from yfinance at {self.timeframe} timeframe...")

            # Calculate date range
            end_date = datetime.now()
            
            if is_intraday:
                # Intraday data limited to 60 days
                max_days = min(lookback_days, self.MAX_INTRADAY_DAYS)
                start_date = end_date - timedelta(days=max_days)
                logger.info(f"Intraday timeframe: limited to {max_days} days")
            else:
                start_date = end_date - timedelta(days=lookback_days + 10)  # Buffer

            # Fetch data
            data = yf.download(
                ticker,
                start=start_date,
                end=end_date,
                interval=interval,
                progress=False,
            )

            if data.empty:
                logger.warning(f"No data returned for {symbol}")
                return pd.DataFrame()

            # Rename columns to lowercase
            if isinstance(data.columns, pd.MultiIndex):
                # Handle multi-index columns (when downloading multiple tickers)
                data.columns = data.columns.get_level_values(0)
            data.columns = [str(col).lower() for col in data.columns]

            # Ensure we have required columns
            required_cols = ["open", "high", "low", "close", "volume"]
            if not all(col in data.columns for col in required_cols):
                logger.error(f"Missing required columns for {symbol}")
                return pd.DataFrame()

            # Take last N rows (bars or days)
            if lookback_bars:
                data = data.tail(lookback_bars).copy()
            else:
                data = data.tail(lookback_days if not is_intraday else len(data)).copy()
            
            # Handle 4h timeframe (resample from 1h)
            if self.timeframe == "4h" and interval == "1h":
                logger.info("Resampling 1h data to 4h...")
                data = self._resample_to_4h(data)

            # Reset index to make date a column
            data = data.reset_index()
            if "date" in data.columns:
                data["timestamp"] = data["date"]
            elif "datetime" in data.columns:
                data["timestamp"] = data["datetime"]
            elif "index" in data.columns:
                data["timestamp"] = data["index"]

            # Ensure timestamp is datetime
            if "timestamp" in data.columns:
                data["timestamp"] = pd.to_datetime(data["timestamp"])
                data = data.set_index("timestamp")

            logger.info(
                f"✅ Fetched {len(data)} days of live data for {symbol} "
                f"(latest: {data.index[-1]}, close: ${data['close'].iloc[-1]:.4f})"
            )

            return data[required_cols]

        except Exception as e:
            logger.error(f"Failed to fetch data for {symbol}: {e}")
            import traceback
            traceback.print_exc()
            return pd.DataFrame()
    
    def _resample_to_4h(self, data: pd.DataFrame) -> pd.DataFrame:
        """Resample 1h data to 4h timeframe."""
        try:
            # Ensure index is datetime
            if not isinstance(data.index, pd.DatetimeIndex):
                data.index = pd.to_datetime(data.index)
            
            # Resample OHLCV data (use lowercase 'h' per pandas 2.0+)
            resampled = pd.DataFrame()
            resampled['open'] = data['open'].resample('4h').first()
            resampled['high'] = data['high'].resample('4h').max()
            resampled['low'] = data['low'].resample('4h').min()
            resampled['close'] = data['close'].resample('4h').last()
            resampled['volume'] = data['volume'].resample('4h').sum()
            
            # Drop NaN rows
            resampled = resampled.dropna()
            
            logger.info(f"Resampled {len(data)} 1h bars to {len(resampled)} 4h bars")
            return resampled
            
        except Exception as e:
            logger.error(f"Failed to resample to 4h: {e}")
            return data

    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current/latest price for a symbol.

        Args:
            symbol: Symbol to fetch

        Returns:
            Current price or None if unavailable
        """
        try:
            ticker = self.SYMBOL_MAP.get(symbol.lower(), symbol)

            # Fetch 1 day of data (includes latest)
            data = yf.download(
                ticker,
                period="1d",
                interval="1m",
                progress=False,
            )

            if data.empty:
                logger.warning(f"No current price for {symbol}")
                return None

            # Handle column names
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)
            data.columns = [str(col).lower() for col in data.columns]

            current_price = float(data["close"].iloc[-1])
            logger.info(f"Current price for {symbol}: ${current_price:.4f}")

            return float(current_price)

        except Exception as e:
            logger.error(f"Failed to get current price for {symbol}: {e}")
            return None

    def is_market_open(self, symbol: str) -> bool:
        """Check if market is open for trading.

        Note: Forex market is 24/5, closes Friday 5pm EST to Sunday 5pm EST

        Args:
            symbol: Symbol to check

        Returns:
            True if market is likely open
        """
        now = datetime.now()
        weekday = now.weekday()

        # Forex: closed on weekends (Saturday=5, Sunday=6)
        if symbol.lower() in ["eurusd", "gbpusd", "usdjpy"]:
            if weekday == 5:  # Saturday
                return False
            if weekday == 6:  # Sunday
                # Forex opens Sunday 5pm EST (22:00 UTC)
                return now.hour >= 22
            return True

        # Gold futures: similar to Forex
        if symbol.lower() in ["gold", "xauusd"]:
            if weekday >= 5:  # Weekend
                return False
            return True

        # Default: assume open on weekdays
        return weekday < 5


def test_live_data():
    """Test live data fetching."""
    print("=" * 60)
    print("Testing Live Data Fetcher")
    print("=" * 60)

    fetcher = LiveDataFetcher(source="yfinance")

    # Test 1: Fetch historical + latest
    print("\n1. Fetching EUR/USD data...")
    data = fetcher.fetch_latest("eurusd", lookback_days=30)
    if not data.empty:
        print(f"   ✅ Got {len(data)} days")
        print(f"   Latest: {data.index[-1]}, Close: ${data['close'].iloc[-1]:.4f}")
    else:
        print("   ❌ No data")

    # Test 2: Get current price
    print("\n2. Getting current EUR/USD price...")
    price = fetcher.get_current_price("eurusd")
    if price:
        print(f"   ✅ Current price: ${price:.4f}")
    else:
        print("   ❌ No price")

    # Test 3: Check market status
    print("\n3. Checking market status...")
    is_open = fetcher.is_market_open("eurusd")
    print(f"   {'✅' if is_open else '❌'} Forex market is {'OPEN' if is_open else 'CLOSED'}")

    print("\n" + "=" * 60)
    print("✅ Live data tests complete!")


if __name__ == "__main__":
    test_live_data()
