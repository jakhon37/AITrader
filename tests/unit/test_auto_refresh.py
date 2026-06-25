"""Unit tests for background data refresh worker."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.core.config import AppConfig, DataConfig, DataPipelineConfig
from src.data.pipeline.auto_refresh import DataRefreshWorker


def _cfg(auto: bool = True) -> AppConfig:
    return AppConfig(
        data=DataConfig(
            source="dukascopy",
            pipeline=DataPipelineConfig(
                auto_refresh=auto,
                tail_refresh_interval_sec=600,
            ),
        )
    )


@pytest.mark.asyncio
async def test_worker_runs_tail_refresh() -> None:
    store = MagicMock()
    worker = DataRefreshWorker(store=store, cfg=_cfg())

    with patch(
        "src.data.pipeline.auto_refresh.refresh_all_enabled",
        return_value={"EURUSD": 100},
    ) as mock_refresh:
        await worker._run_tail_refresh()

    mock_refresh.assert_called_once()
    status = worker.get_status()
    assert status["last_refresh_rows"] == {"EURUSD": 100}
    assert status["last_refresh_at"] is not None


@pytest.mark.asyncio
async def test_worker_disabled_when_auto_refresh_off() -> None:
    store = MagicMock()
    worker = DataRefreshWorker(store=store, cfg=_cfg(auto=False))
    await worker.start()
    assert worker.get_status()["enabled"] is False
    assert worker.get_status()["running"] is False