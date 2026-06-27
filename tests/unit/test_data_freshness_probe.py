"""Unit tests for data freshness probe."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.core.contracts import Instrument, Timeframe
from src.ops.probes.data_freshness_probe import DataFreshnessProbe


def test_age_uses_bar_close_not_open() -> None:
    probe = DataFreshnessProbe(store=MagicMock())
    now = datetime(2026, 6, 26, 14, 50, tzinfo=timezone.utc)
    # H1 bar opened 13:00 closes 14:00 → 50m old at 14:50
    age = probe._age_minutes(
        datetime(2026, 6, 26, 13, 0, tzinfo=timezone.utc),
        Timeframe.H1,
        now,
    )
    assert 49.0 < age < 51.0