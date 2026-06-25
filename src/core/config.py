"""AITrader configuration — replaces and absorbs src/config.py.

Additions over the legacy config:
  - InstrumentConfig: typed model for per-instrument instruments.yaml block
  - CoreConfig.bus_backend: "memory" | "redis"
  - CoreConfig.execution_mode: ExecutionMode
  - load_instruments() -> dict[Instrument, InstrumentConfig]

Usage:
    from src.core.config import AppConfig, load_config, load_instruments

    cfg = load_config()                         # reads ENV + CONFIG_DIR env vars
    instruments = load_instruments()            # reads config/instruments.yaml

Backward compatibility:
    The old src/config.py public surface (AppConfig, load_config, DataConfig,
    ModelConfig, RiskConfig, ExecutionConfig) is fully preserved.
    Existing code that imports from src.config should be updated to src.core.config,
    but src/config.py re-exports from here for a smooth migration window.
"""

from __future__ import annotations

import os
from pathlib import Path

def load_env_file() -> None:
    """Find and load .env file from the project root into os.environ."""
    start_dir = Path.cwd()
    search_dirs = [start_dir] + list(start_dir.parents)[:3]
    module_dir = Path(__file__).resolve().parent
    search_dirs.extend([module_dir, module_dir.parent, module_dir.parent.parent])
    
    seen = set()
    for d in search_dirs:
        try:
            d_resolved = d.resolve()
            if d_resolved in seen:
                continue
            seen.add(d_resolved)
            env_path = d_resolved / ".env"
            if env_path.is_file():
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if "=" in line:
                            parts = line.split("=", 1)
                            key = parts[0].strip()
                            val = parts[1].strip().strip("'\"")
                            if key and key not in os.environ:
                                os.environ[key] = val
                break
        except Exception:
            pass

# Load .env automatically
load_env_file()
from typing import Any, Dict, List, Optional, Union

import yaml
from pydantic import BaseModel, Field

from src.core.contracts import ExecutionMode, Instrument, Timeframe
from src.core.exceptions import ConfigError


# ── Legacy sub-configs (preserved for backward compatibility) ─────────────────

class DataPipelineConfig(BaseModel):
    """Automated refresh cadence for the Dukascopy pipeline."""

    tail_days: int = Field(ge=1, le=90, default=14)
    full_lookback_days: int = Field(ge=30, le=365 * 10, default=365 * 5)
    live_poll_adaptive: bool = Field(
        default=True,
        description="Align live poll cadence to candle close (slower mid-candle for 1h/1d)",
    )
    live_poll_sec_m1: int = Field(ge=10, le=300, default=60)
    live_poll_sec_focused: float = Field(
        ge=1.0,
        le=60.0,
        default=2.0,
        description="Fixed focused poll when live_poll_adaptive=false",
    )
    live_poll_sec_background: float = Field(
        ge=5.0,
        le=120.0,
        default=10.0,
        description="Fixed background poll when live_poll_adaptive=false",
    )
    auto_refresh: bool = Field(
        default=True,
        description="Run tail refresh automatically in the API backend",
    )
    tail_refresh_interval_sec: int = Field(
        ge=300,
        le=86400 * 7,
        default=3600,
        description="M1 tail fetch + M5–H1 resample interval (default 1h)",
    )
    tail_resample_slow_interval_sec: int = Field(
        ge=3600,
        le=86400 * 7,
        default=86400,
        description="4h/1d resample from stored M1 (default 1/day)",
    )
    live_m1_cache_ttl_sec: float = Field(
        ge=5.0,
        le=300.0,
        default=30.0,
        description="Reuse one M1 download across live timeframe polls (seconds)",
    )
    dukascopy_tick_enabled: bool = Field(
        default=True,
        description="Use hourly tick files for current UTC day (daily .bi5 is T-1)",
    )


class DataInstrumentEntry(BaseModel):
    """Deprecated — use ``enabled`` on each block in config/instruments.yaml instead."""

    symbol: str = Field(description="Instrument enum value, e.g. EURUSD")
    enabled: bool = Field(default=True)
    dukascopy_symbol: Optional[str] = Field(
        default=None, description="Override Dukascopy symbol (defaults to symbol)"
    )


class DataConfig(BaseModel):
    """Data layer: symbols, lookback, paths (no secrets)."""

    symbols: List[str] = Field(default_factory=lambda: ["EUR_USD", "GBP_USD", "USD_JPY"])
    lookback_days: int = Field(ge=1, le=365 * 10, default=365 * 5)
    data_dir: str = Field(default="data")
    data_version: Optional[str] = Field(
        default=None, description="Data version tag for reproducibility"
    )
    timeframe: str = Field(
        default="1d",
        description="Data timeframe: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 1mo",
    )
    source: str = Field(
        default="dukascopy",
        description="Primary OHLCV source: dukascopy (yahoo deprecated for live)",
    )
    pipeline: DataPipelineConfig = Field(default_factory=DataPipelineConfig)
    instruments: List[DataInstrumentEntry] = Field(
        default_factory=list,
        description="Deprecated fallback; prefer instruments.yaml enabled flags",
    )


class ModelConfig(BaseModel):
    """Models: paths, hyperparameters, ensemble weights."""

    checkpoint_dir: str = Field(default="checkpoints")
    ensemble_weights: dict[str, float] = Field(default_factory=dict)
    confidence_threshold: float = Field(ge=0.0, le=1.0, default=0.55)
    model_type: str = Field(
        default="lstm_transformer",
        description=(
            "Model to use: lightgbm, xgboost, enhanced_transformer, "
            "lstm_transformer, garch_gru"
        ),
    )
    batch_size: int = Field(default=256, ge=8, le=4096)
    epochs: int = Field(default=50, ge=1, le=1000)

    # Neural network specific
    hidden_size: int = Field(default=128, ge=32, le=512)
    num_layers: int = Field(default=2, ge=1, le=5)
    dropout: float = Field(default=0.2, ge=0.0, le=0.5)
    learning_rate: float = Field(default=0.001, ge=0.00001, le=0.1)
    seq_length: int = Field(default=20, ge=5, le=200)

    # Enhanced Transformer specific
    d_model: int = Field(default=256, ge=64, le=1024)
    nhead: int = Field(default=8, ge=2, le=16)
    num_transformer_layers: int = Field(default=4, ge=1, le=8)
    dim_feedforward: int = Field(default=1024, ge=256, le=4096)

    # Tree-based models
    n_estimators: int = Field(default=500, ge=50, le=5000)
    max_depth: int = Field(default=7, ge=3, le=15)
    tree_learning_rate: float = Field(default=0.01, ge=0.001, le=0.5)
    subsample: float = Field(default=0.8, ge=0.5, le=1.0)
    colsample_bytree: float = Field(default=0.8, ge=0.5, le=1.0)
    reg_alpha: float = Field(default=0.1, ge=0.0, le=10.0)
    reg_lambda: float = Field(default=0.1, ge=0.0, le=10.0)


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


class FundamentalConfig(BaseModel):
    """D03: fundamental analysis settings (sentiment, polling, aggregation)."""

    sentiment_backend: str = Field(
        default="mock",
        description="finbert | mock | openrouter. 'mock' recommended for low-RAM CPU dev machines.",
        pattern="^(finbert|mock|openrouter)$",
    )
    poll_interval_seconds: int = Field(
        default=600, ge=60, le=3600,
        description="How often the FundamentalAgent polls for new news articles"
    )
    aggregation_window_minutes: int = Field(
        default=15, ge=1, le=120,
        description="Time window to aggregate multiple articles into one FundamentalSignal"
    )
    min_confidence_to_emit: float = Field(
        default=0.25, ge=0.0, le=1.0,
        description="Minimum confidence before publishing a FundamentalSignal"
    )
    enable_structured_llm: bool = Field(
        default=True,
        description="Use structured output from OpenRouter for sentiment when backend=openrouter"
    )
    calendar_briefing_enabled: bool = Field(
        default=True,
        description="Generate pre-release calendar briefings via OpenRouter and publish to UI/Telegram",
    )
    calendar_min_impact: str = Field(
        default="medium",
        pattern="^(low|medium|high)$",
        description="Minimum calendar impact level to emit a pre-release briefing",
    )
    calendar_telegram_min_impact: str = Field(
        default="high",
        pattern="^(low|medium|high)$",
        description="Minimum impact for Telegram pre-release calendar alerts",
    )


# ── New D01 additions ─────────────────────────────────────────────────────────

class SignalDecayConfig(BaseModel):
    """Per-event-type signal decay hours (configurable per instrument)."""

    central_bank:   float = Field(default=48.0)
    economic_data:  float = Field(default=4.0)
    geopolitical:   float = Field(default=6.0)
    market_risk:    float = Field(default=2.0)
    technical_conf: float = Field(default=1.0)


class DailyBreakConfig(BaseModel):
    """Intraday maintenance window (e.g. XAUUSD 21:00–22:00 UTC)."""

    start: str = Field(description="UTC HH:MM inclusive")
    end: str = Field(description="UTC HH:MM when session reopens")


class InstrumentConfig(BaseModel):
    """Per-instrument trading configuration loaded from config/instruments.yaml.

    All divisions load instrument config via src.core.config.InstrumentConfig.
    See CONTRACTS.md for the full YAML shape.
    """

    enabled:            bool = Field(
        default=True,
        description="Include in Dukascopy refresh, live scheduler, and chart UI",
    )
    pip_size:           float
    lot_size:           float
    session_hours:      dict[str, str]          # {"open": "22:00", "close": "22:00"} UTC
    daily_break:        Optional[DailyBreakConfig] = Field(
        default=None,
        description="Optional 1h pause before daily reopen (gold)",
    )
    active_timeframes:  List[Timeframe]
    primary_timeframe:  Timeframe
    fundamental_weight: float = Field(ge=0.0, le=1.0, default=0.3)
    technical_weight:   float = Field(ge=0.0, le=1.0, default=0.7)
    max_position_lots:  float = Field(gt=0.0, default=1.0)
    news_halt_minutes:  int   = Field(ge=0, default=30)
    signal_decay:       SignalDecayConfig = Field(default_factory=SignalDecayConfig)


class CoreConfig(BaseModel):
    """D01-level infrastructure knobs."""

    bus_backend:    str           = Field(default="memory", pattern="^(memory|redis)$")
    execution_mode: ExecutionMode = Field(default=ExecutionMode.PAPER)


# ── Root AppConfig ────────────────────────────────────────────────────────────

class AppConfig(BaseModel):
    """Root config: env name and all nested sections."""

    env:         str           = Field(default="dev", pattern="^(dev|staging|prod)$")
    core:        CoreConfig    = Field(default_factory=CoreConfig)
    data:        DataConfig    = Field(default_factory=DataConfig)
    model:       ModelConfig   = Field(default_factory=ModelConfig)
    risk:        RiskConfig    = Field(default_factory=RiskConfig)
    execution:   ExecutionConfig = Field(default_factory=ExecutionConfig)
    fundamental: FundamentalConfig = Field(default_factory=FundamentalConfig)
    notifier:    dict          = Field(default_factory=dict)  # telegram etc.

    @classmethod
    def from_yaml(cls, path: str | Path) -> "AppConfig":
        """Load from YAML file.  Secrets must come from env vars, not the file."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        with open(path) as f:
            raw: dict[str, Any] = yaml.safe_load(f) or {}
        return cls.model_validate(raw)

    @classmethod
    def from_env(cls, config_dir: Optional[Union[str, Path]] = None) -> "AppConfig":
        """Load config for the current environment.

        Reads CONFIG_DIR env var (default: 'config') and ENV env var (default: 'dev').
        Looks for config/<ENV>.yaml.
        """
        config_dir = Path(config_dir or os.getenv("CONFIG_DIR", "config"))
        env = os.getenv("ENV", "dev")
        path = config_dir / f"{env}.yaml"
        if not path.exists():
            raise ConfigError(
                f"Config not found: {path}. "
                f"Set ENV=dev|staging|prod and ensure the config file exists."
            )
        return cls.from_yaml(path)

    def get_symbols_normalized(self) -> List[str]:
        """Return enabled instrument ids (lowercase) for training/download scripts."""
        try:
            from src.core.instruments import get_enabled_instruments

            enabled = [inst.value.lower() for inst in get_enabled_instruments()]
            if enabled:
                return enabled
        except Exception:
            pass
        return [s.lower().replace("_", "") for s in self.data.symbols]

    def get_primary_symbol(self) -> str:
        """Return the first enabled instrument in normalized format."""
        syms = self.get_symbols_normalized()
        return syms[0] if syms else "eurusd"


# ── Instruments loader ────────────────────────────────────────────────────────

def load_instruments(
    instruments_path: Optional[Union[str, Path]] = None,
) -> dict[Instrument, InstrumentConfig]:
    """Load per-instrument configuration from YAML.

    Default path: config/instruments.yaml (relative to CONFIG_DIR env var).
    Returns a dict keyed by Instrument enum.

    Raises:
        ConfigError: if the file is missing or any instrument block is invalid.
    """
    config_dir = Path(os.getenv("CONFIG_DIR", "config"))
    path = Path(instruments_path) if instruments_path else config_dir / "instruments.yaml"

    if not path.exists():
        raise ConfigError(
            f"instruments.yaml not found: {path}. "
            f"Create it or set CONFIG_DIR to the correct config directory."
        )

    with open(path) as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}

    result: dict[Instrument, InstrumentConfig] = {}
    for key, block in raw.items():
        try:
            instrument = Instrument(key.upper())
        except ValueError as exc:
            raise ConfigError(
                f"Unknown instrument in instruments.yaml: {key!r}. "
                f"Valid values: {[e.value for e in Instrument]}"
            ) from exc
        try:
            result[instrument] = InstrumentConfig.model_validate(block)
        except Exception as exc:  # noqa: BLE001
            raise ConfigError(
                f"Invalid InstrumentConfig for {key}: {exc}"
            ) from exc

    return result


# ── Convenience loader ────────────────────────────────────────────────────────

def load_config(config_path: Optional[Union[str, Path]] = None) -> AppConfig:
    """Load AppConfig from a specific file, or from ENV + CONFIG_DIR env vars."""
    if config_path:
        return AppConfig.from_yaml(config_path)
    return AppConfig.from_env()
