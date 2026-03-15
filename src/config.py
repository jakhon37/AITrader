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
    model_type: str = Field(
        default="lstm_transformer", 
        description="Model to use: lightgbm, xgboost, enhanced_transformer, lstm_transformer, garch_gru"
    )
    batch_size: int = Field(default=256, ge=8, le=4096, description="Training batch size (neural nets)")
    epochs: int = Field(default=50, ge=1, le=1000, description="Training epochs (neural nets)")
    
    # Neural network specific (LSTM-Transformer, GARCH-GRU)
    hidden_size: int = Field(default=128, ge=32, le=512, description="Hidden size for LSTM/GRU models")
    num_layers: int = Field(default=2, ge=1, le=5, description="Number of layers")
    dropout: float = Field(default=0.2, ge=0.0, le=0.5, description="Dropout rate")
    learning_rate: float = Field(default=0.001, ge=0.00001, le=0.1, description="Learning rate for neural nets")
    seq_length: int = Field(default=20, ge=5, le=200, description="Sequence length for sequential models")
    
    # Enhanced Transformer specific
    d_model: int = Field(default=256, ge=64, le=1024, description="Model dimension for enhanced transformer")
    nhead: int = Field(default=8, ge=2, le=16, description="Number of attention heads")
    num_transformer_layers: int = Field(default=4, ge=1, le=8, description="Number of transformer layers")
    dim_feedforward: int = Field(default=1024, ge=256, le=4096, description="Feedforward dimension")
    
    # Tree-based models (LightGBM, XGBoost)
    n_estimators: int = Field(default=500, ge=50, le=5000, description="Number of trees/boosting rounds")
    max_depth: int = Field(default=7, ge=3, le=15, description="Maximum tree depth")
    tree_learning_rate: float = Field(default=0.01, ge=0.001, le=0.5, description="Learning rate for tree models")
    subsample: float = Field(default=0.8, ge=0.5, le=1.0, description="Subsample ratio")
    colsample_bytree: float = Field(default=0.8, ge=0.5, le=1.0, description="Column sampling ratio")
    reg_alpha: float = Field(default=0.1, ge=0.0, le=10.0, description="L1 regularization")
    reg_lambda: float = Field(default=0.1, ge=0.0, le=10.0, description="L2 regularization")


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

