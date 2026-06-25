"""Instrument registry — enabled set from config/instruments.yaml."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.core.config import load_instruments
from src.core.contracts import Instrument

if TYPE_CHECKING:
    from src.core.config import AppConfig


def get_enabled_instruments(_cfg: AppConfig | None = None) -> list[Instrument]:
    """Instruments with ``enabled: true`` in instruments.yaml.

    ``_cfg`` is accepted for backward compatibility but ignored — instrument
    activation lives in instruments.yaml per DEV_PLAN.
    """
    configs = load_instruments()
    enabled = [
        inst
        for inst in Instrument
        if inst in configs and configs[inst].enabled
    ]
    return enabled if enabled else list(Instrument)