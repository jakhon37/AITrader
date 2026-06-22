"""Backward-compatibility shim — imports have moved to src.core.config.

Update all imports to:
    from src.core.config import AppConfig, load_config, ...

This file will be removed once all callers are migrated.
"""

from src.core.config import (  # noqa: F401 — re-export for migration window
    AppConfig,
    CoreConfig,
    DataConfig,
    ExecutionConfig,
    InstrumentConfig,
    ModelConfig,
    RiskConfig,
    SignalDecayConfig,
    load_config,
    load_instruments,
)
