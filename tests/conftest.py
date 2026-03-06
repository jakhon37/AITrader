"""Pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def config_dir() -> Path:
    """Path to config directory (project root / config)."""
    return Path(__file__).resolve().parent.parent / "config"


@pytest.fixture
def dev_config_path(config_dir: Path) -> Path:
    """Path to dev.yaml."""
    return config_dir / "dev.yaml"
