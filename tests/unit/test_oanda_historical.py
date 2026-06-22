"""Unit tests for the OANDA historical data loader with chunked pagination and fallbacks."""

from __future__ import annotations

import lzma
import struct
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import pandas as pd
import pytest

from src.core.contracts import Instrument, Timeframe
from src.data.loaders.oanda_historical import OANDAHistoricalLoader


def generate_mock_bi5() -> bytes:
    # Generate 1 candle record: time_sec = 60, open=108500, close=108550, low=108400, high=108600, volume=120.0
    # Format: >5If (Big-endian, 5 unsigned ints, 1 float)
    fmt = ">5If"
    record = struct.pack(fmt, 60, 108500, 108550, 108400, 108600, 120.0)
    return lzma.compress(record)


@patch("requests.get")
def test_oanda_loader_chunked_pagination(mock_get: MagicMock) -> None:
    """Verify that OANDAHistoricalLoader splits long OANDA queries into multiple requests."""
    # OANDA credentials mock
    loader = OANDAHistoricalLoader(
        api_token="test_token",
        account_id="test_account",
        environment="practice"
    )

    start = datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 6, 8, 0, 0, tzinfo=timezone.utc)

    # Mock OANDA REST returns
    def side_effect(url: str, headers: dict = None, params: dict = None, timeout: float = None) -> MagicMock:
        res = MagicMock()
        res.ok = True
        
        # Determine unique candle time in this chunk
        c_time = params["from"]
        res.json.return_value = {
            "candles": [
                {
                    "complete": True,
                    "time": c_time,
                    "mid": {"o": "1.0850", "h": "1.0860", "l": "1.0840", "c": "1.0855"},
                    "volume": 120.0,
                }
            ]
        }
        return res

    mock_get.side_effect = side_effect

    # Fetch history
    df = loader.fetch_history(Instrument.EURUSD, Timeframe.M1, start, end)

    # Verify OANDA was called 3 times (due to M1 chunk_delta being 3 days, 7 days total)
    assert mock_get.call_count == 3
    assert len(df) == 3
    assert isinstance(df.index, pd.DatetimeIndex)
    assert df.index.tz == timezone.utc
    assert list(df["open"]) == [1.0850, 1.0850, 1.0850]


@patch("requests.get")
def test_oanda_loader_fallback_to_dukascopy(mock_get: MagicMock) -> None:
    """Verify that if OANDA credentials are empty, it falls back to Dukascopy."""
    # Empty OANDA credentials
    loader = OANDAHistoricalLoader(api_token=None, account_id=None)

    start = datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 6, 1, 23, 59, tzinfo=timezone.utc)

    # Mock Dukascopy binary response
    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.content = generate_mock_bi5()
    mock_get.return_value = mock_res

    df = loader.fetch_history(Instrument.EURUSD, Timeframe.M1, start, end)

    assert mock_get.called
    # Dukascopy URL check
    call_url = mock_get.call_args[0][0]
    assert "datafeed.dukascopy.com" in call_url
    assert len(df) == 1
    assert df.index[0] == datetime(2026, 6, 1, 0, 1, tzinfo=timezone.utc)
    assert df["open"].iloc[0] == 1.085
    assert df["high"].iloc[0] == 1.086
    assert df["low"].iloc[0] == 1.084
    assert df["close"].iloc[0] == 1.0855


@patch("yfinance.download")
@patch("requests.get")
def test_oanda_loader_fallback_to_yfinance(mock_get: MagicMock, mock_yf: MagicMock) -> None:
    """Verify that if both OANDA and Dukascopy fail, it falls back to yfinance."""
    loader = OANDAHistoricalLoader(api_token=None, account_id=None)

    # Mock Dukascopy failing (status_code 404 or exception)
    mock_res = MagicMock()
    mock_res.status_code = 404
    mock_get.return_value = mock_res

    # Mock yfinance return
    idx = pd.date_range(start="2026-06-01 00:00:00", periods=2, freq="1d", tz="UTC")
    mock_df = pd.DataFrame(
        {
            "Open": [1.08, 1.09],
            "High": [1.09, 1.10],
            "Low": [1.07, 1.08],
            "Close": [1.085, 1.095],
            "Volume": [1000, 1100],
        },
        index=idx,
    )
    mock_yf.return_value = mock_df

    start = datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 6, 3, 0, 0, tzinfo=timezone.utc)

    df = loader.fetch_history(Instrument.EURUSD, Timeframe.D1, start, end)

    assert mock_get.called
    assert mock_yf.called
    assert len(df) == 2
    assert "open" in df.columns
    assert df["open"].iloc[0] == 1.08
