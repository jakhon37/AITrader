"""Load and validate configuration. Fails fast on missing/invalid config."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class DataConfig(BaseModel):
    """Data layer: symbols, lookback, paths (no secrets)."""

    symbols: list[str] = Field(default_factory=lambda: ["EUR_USD", "GBP_USD", "USD_JPY"])
    lookback_days: int = Field(ge=1, le=365 * 10, default=365 * 5)
    data_dir: str = Field(default="data")
    data_version: str | None = Field(
        default=None, description="Data version tag for reproducibility"
    )
    timeframe: str = Field(default="1d", description="Data timeframe: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 1mo")


class ModelConfig(BaseModel):
    """Models: paths, hyperparameters, ensemble weights."""

    checkpoint_dir: str = Field(default="checkpoints")
    ensemble_weights: dict[str, float] = Field(default_factory=dict)
    confidence_threshold: float = Field(ge=0.0, le=1.0, default=0.55)
    model_type: str = Field(default="lstm_transformer", description="Model to use: lstm_transformer, garch_gru")
    batch_size: int = Field(default=256, ge=8, le=4096, description="Training batch size")
    epochs: int = Field(default=50, ge=1, le=1000, description="Training epochs")


class RiskConfig(BaseModel):
    """Risk: position limits, drawdown, circuit breakers."""

    max_position_pct: float = Field(ge=0.01, le=1.0, default=0.02)
    max_drawdown_pct: float = Field(ge=0.01, le=0.5, default=0.10)
    daily_loss_limit_pct: float = Field(ge=0.01, le=0.2, default=0.03)
    max_signals_per_day: int = Field(ge=1, le=500, default=50)


class ExecutionConfig(BaseModel):
    """Execution: broker name, rate limits, slippage (no API keys)."""

    broker: str = Field(default="mock")
    slippage_pips: float = Field(ge=0.0, le=10.0, default=0.5)
    rate_limit_per_min: int = Field(ge=1, le=120, default=30)


class AppConfig(BaseModel):
    """Root config: env name and nested sections."""

    env: str = Field(default="dev", pattern="^(dev|staging|prod)$")
    data: DataConfig = Field(default_factory=DataConfig)
    model: ModelConfig = Field(default_factory=ModelConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)

    @classmethod
    def from_yaml(cls, path: str | Path) -> AppConfig:
        """Load from YAML file. Secrets must come from env, not file."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        with open(path) as f:
            raw: dict[str, Any] = yaml.safe_load(f) or {}
        return cls.model_validate(raw)

    @classmethod
    def from_env(cls, config_dir: str | Path | None = None) -> AppConfig:
        """
        Load config for current environment.
        Uses CONFIG_PATH if set, else config/<ENV>.yaml (ENV defaults to 'dev').
        """
        config_dir = Path(config_dir or os.getenv("CONFIG_DIR", "config"))
        env = os.getenv("ENV", "dev")
        path = config_dir / f"{env}.yaml"
        if not path.exists():
            raise FileNotFoundError(
                f"Config not found: {path}. Set ENV=dev|staging|prod and ensure config file exists."
            )
        return cls.from_yaml(path)
    
    def get_symbols_normalized(self) -> list[str]:
        """Get symbols in normalized format (lowercase with no underscore).
        
        Converts: EUR_USD -> eurusd, BTC_USD -> btcusd
        """
        return [s.lower().replace("_", "") for s in self.data.symbols]
    
    def get_primary_symbol(self) -> str:
        """Get the first symbol in normalized format."""
        symbols = self.get_symbols_normalized()
        return symbols[0] if symbols else "eurusd"


def load_config(config_path: str | Path | None = None) -> AppConfig:
    """Convenience function to load config from file or environment."""
    if config_path:
        return AppConfig.from_yaml(config_path)
    return AppConfig.from_env()

