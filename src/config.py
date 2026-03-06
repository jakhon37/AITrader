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


class ModelConfig(BaseModel):
    """Models: paths, hyperparameters, ensemble weights."""

    checkpoint_dir: str = Field(default="checkpoints")
    ensemble_weights: dict[str, float] = Field(default_factory=dict)
    confidence_threshold: float = Field(ge=0.0, le=1.0, default=0.55)


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
