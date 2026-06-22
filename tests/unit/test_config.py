"""Unit tests for config loading and validation."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from config import AppConfig, DataConfig, RiskConfig


class TestAppConfig:
    """Test AppConfig from YAML and from_env."""

    def test_load_dev_yaml(self, dev_config_path: Path) -> None:
        """Load dev.yaml and check structure."""
        if not dev_config_path.exists():
            pytest.skip("config/dev.yaml not found")
        cfg = AppConfig.from_yaml(dev_config_path)
        assert cfg.env == "dev"
        assert len(cfg.data.symbols) > 0   # dev.yaml has GOLD, BTC_USD, EUR_USD, ...
        assert cfg.risk.max_drawdown_pct > 0

    def test_from_env_uses_dev_by_default(self, config_dir: Path) -> None:
        """With ENV unset, from_env loads dev.yaml."""
        if not (config_dir / "dev.yaml").exists():
            pytest.skip("config/dev.yaml not found")
        prev = os.environ.pop("ENV", None)
        os.environ.pop("CONFIG_DIR", None)
        try:
            cfg = AppConfig.from_env(config_dir=config_dir)
            assert cfg.env == "dev"
        finally:
            if prev is not None:
                os.environ["ENV"] = prev

    def test_missing_config_raises(self) -> None:
        """Missing config file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="not found"):
            AppConfig.from_yaml(Path("/nonexistent/config.yaml"))

    def test_invalid_env_rejected(self) -> None:
        """Invalid env value is rejected by Pydantic."""
        with pytest.raises(ValidationError):
            AppConfig(env="invalid")

    def test_risk_bounds(self) -> None:
        """Risk config enforces bounds."""
        with pytest.raises(ValidationError):
            RiskConfig(max_drawdown_pct=2.0)  # > 0.5
        cfg = RiskConfig(max_drawdown_pct=0.10)
        assert cfg.max_drawdown_pct == 0.10

    def test_data_config_defaults(self) -> None:
        """DataConfig has expected defaults."""
        cfg = DataConfig()
        assert "EUR_USD" in cfg.symbols
        assert cfg.lookback_days >= 365
