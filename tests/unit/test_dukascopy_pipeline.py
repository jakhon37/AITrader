"""Unit tests for Dukascopy feed parsing, merge guard, and refresh helpers."""

from __future__ import annotations

import lzma
import struct
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.core.contracts import Instrument, Timeframe
from src.data.feeds.dukascopy import DukascopyFeed, _parse_bi5_day, bars_from_m1_df
from src.data.feeds.dukascopy_ticks import parse_tick_hour, ticks_to_m1
from src.data.pipeline.merge import is_flat_bar, merge_ohlcv_without_downgrade
from src.data.pipeline.refresh import refresh_instrument


def _make_bi5_record(
    time_sec: int,
    open_p: int,
    close_p: int,
    low_p: int,
    high_p: int,
    volume: float,
) -> bytes:
    return struct.pack(">5If", time_sec, open_p, close_p, low_p, high_p, volume)


class TestBi5Parse:
    def test_parse_bi5_day_scales_prices(self) -> None:
        records = _make_bi5_record(60, 110_000, 110_050, 109_950, 110_100, 42.0)
        records += _make_bi5_record(120, 110_050, 110_080, 110_020, 110_090, 35.0)
        payload = lzma.compress(records)

        df = _parse_bi5_day(payload, 2024, 6, 10, divisor=100_000.0)
        assert len(df) == 2
        assert df.iloc[0]["open"] == pytest.approx(1.10)
        assert df.iloc[0]["high"] >= df.iloc[0]["low"]
        assert df.iloc[0]["volume"] == pytest.approx(42.0)


class TestMergeGuard:
    def test_flat_bar_does_not_downgrade_wicks(self) -> None:
        idx = pd.DatetimeIndex([datetime(2024, 6, 10, 9, 0, tzinfo=timezone.utc)])
        existing = pd.DataFrame(
            {"open": [1.10], "high": [1.101], "low": [1.099], "close": [1.1005], "volume": [300.0]},
            index=idx,
        )
        incoming = pd.DataFrame(
            {"open": [1.10], "high": [1.10], "low": [1.10], "close": [1.1006], "volume": [0.0]},
            index=idx,
        )
        merged = merge_ohlcv_without_downgrade(existing, incoming)
        row = merged.iloc[0]
        assert row["high"] > row["low"]
        assert not is_flat_bar(row)
        assert row["close"] == pytest.approx(1.1006)

    def test_wick_bars_merge_high_low(self) -> None:
        idx = pd.DatetimeIndex([datetime(2024, 6, 10, 9, 0, tzinfo=timezone.utc)])
        existing = pd.DataFrame(
            {"open": [1.10], "high": [1.101], "low": [1.099], "close": [1.1005], "volume": [100.0]},
            index=idx,
        )
        incoming = pd.DataFrame(
            {"open": [1.10], "high": [1.102], "low": [1.098], "close": [1.1008], "volume": [200.0]},
            index=idx,
        )
        merged = merge_ohlcv_without_downgrade(existing, incoming)
        row = merged.iloc[0]
        assert row["high"] == pytest.approx(1.102)
        assert row["low"] == pytest.approx(1.098)
        assert row["volume"] == pytest.approx(200.0)


class TestTickAggregation:
    def test_ticks_to_m1_produces_wicks(self) -> None:
        import lzma
        import struct

        rows = b""
        # 3 ticks in same minute at different bid prices
        for ms, bid_i in [(1000, 113500), (15000, 113520), (30000, 113510)]:
            rows += struct.pack(">IIIff", ms, 113510, bid_i, 1.0, 2.0)
        payload = lzma.compress(rows)
        ticks = parse_tick_hour(payload, 2024, 6, 10, 8, divisor=100_000.0)
        m1 = ticks_to_m1(ticks)
        assert len(m1) == 1
        row = m1.iloc[0]
        assert row["high"] > row["low"]
        assert row["volume"] > 0


class TestM1LiveBatch:
    def test_bars_from_m1_df_derives_h1(self) -> None:
        idx = pd.date_range(
            "2024-06-10 08:00",
            periods=120,
            freq="1min",
            tz="UTC",
        )
        m1 = pd.DataFrame(
            {
                "open": [1.10 + i * 0.00001 for i in range(120)],
                "high": [1.1005 + i * 0.00001 for i in range(120)],
                "low": [1.0995 + i * 0.00001 for i in range(120)],
                "close": [1.1002 + i * 0.00001 for i in range(120)],
                "volume": [10.0] * 120,
            },
            index=idx,
        )
        now = datetime(2024, 6, 10, 9, 30, tzinfo=timezone.utc)
        completed, active = bars_from_m1_df(
            Instrument.EURUSD, Timeframe.H1, m1, now=now
        )
        assert completed.timeframe == Timeframe.H1
        assert completed.timestamp == datetime(2024, 6, 10, 8, 0, tzinfo=timezone.utc)
        assert active is not None
        assert active.timestamp == datetime(2024, 6, 10, 9, 0, tzinfo=timezone.utc)

    def test_fetch_m1_recent_uses_cache(self) -> None:
        feed = DukascopyFeed(live_m1_cache_ttl_sec=60.0)
        idx = pd.date_range("2024-06-10", periods=5, freq="1min", tz="UTC")
        stub = pd.DataFrame(
            {
                "open": [1.1] * 5,
                "high": [1.11] * 5,
                "low": [1.09] * 5,
                "close": [1.1] * 5,
                "volume": [1.0] * 5,
            },
            index=idx,
        )
        with patch.object(feed, "_fetch_m1_hybrid", return_value=stub) as mock_fetch:
            first = feed.fetch_m1_recent(Instrument.EURUSD)
            second = feed.fetch_m1_recent(Instrument.EURUSD)
        assert len(first) == 5
        assert len(second) == 5
        mock_fetch.assert_called_once()


class TestRefreshTail:
    def test_refresh_instrument_calls_backfill(self) -> None:
        store = MagicMock()
        store.list_ohlcv_range.return_value = (None, datetime(2024, 6, 20, tzinfo=timezone.utc))
        feed = MagicMock(spec=DukascopyFeed)

        with patch("src.data.pipeline.refresh.backfill_instrument", return_value=42) as mock_bf:
            rows = refresh_instrument(store, feed, Instrument.EURUSD, mode="tail", tail_days=7)
        assert rows == 42
        mock_bf.assert_called_once()