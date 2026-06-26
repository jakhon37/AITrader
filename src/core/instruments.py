"""Instrument registry — enabled set from config/instruments.yaml."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.core.config import load_instruments
from src.core.contracts import Instrument, Timeframe

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


def get_scheduler_active_pairs(_cfg: AppConfig | None = None) -> list[tuple[Instrument, Timeframe]]:
    """Live scheduler pairs: each enabled instrument on its primary timeframe."""
    configs = load_instruments()
    pairs: list[tuple[Instrument, Timeframe]] = []
    for inst in get_enabled_instruments(_cfg):
        cfg = configs.get(inst)
        if cfg is None:
            pairs.append((inst, Timeframe.H1))
            continue
        pairs.append((inst, cfg.primary_timeframe))
    return pairs