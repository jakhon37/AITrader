"""Trading session helpers — UTC boundaries from config/instruments.yaml."""

from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache

from src.core.config import InstrumentConfig, load_instruments
from src.core.contracts import Instrument


def _hour_from_time(time_str: str) -> int:
    return int(time_str.split(":")[0])


@lru_cache(maxsize=1)
def _instrument_configs() -> dict[Instrument, InstrumentConfig]:
    return load_instruments()


def reload_instrument_configs() -> None:
    """Clear cached instruments.yaml after hot-reload."""
    _instrument_configs.cache_clear()


def is_fx_session_open(dt: datetime) -> bool:
    """Standard FX week (Sun 22:00 UTC → Fri 22:00 UTC exclusive)."""
    return is_instrument_session_open(dt, Instrument.EURUSD)


def is_gold_session_open(dt: datetime) -> bool:
    """Dukascopy gold window including daily 21:00–22:00 UTC break."""
    return is_instrument_session_open(dt, Instrument.XAUUSD)


def is_instrument_session_open(dt: datetime, instrument: Instrument) -> bool:
    """Instrument-aware session check driven by instruments.yaml."""
    cfg = _instrument_configs().get(instrument)
    if cfg is None:
        return _fx_weekly_open(dt, open_hour=22, close_hour=22)

    open_hour = _hour_from_time(cfg.session_hours["open"])
    close_hour = _hour_from_time(cfg.session_hours["close"])

    if cfg.daily_break is not None:
        return _gold_session_open(dt, open_hour=open_hour, close_hour=close_hour, cfg=cfg)

    return _fx_weekly_open(dt, open_hour=open_hour, close_hour=close_hour)


def _fx_weekly_open(dt: datetime, *, open_hour: int, close_hour: int) -> bool:
    dt = dt.astimezone(timezone.utc)
    weekday = dt.weekday()
    hour = dt.hour

    if weekday == 5:
        return False
    if weekday == 4 and hour >= close_hour:
        return False
    if weekday == 6 and hour < open_hour:
        return False
    return True


def _gold_session_open(
    dt: datetime,
    *,
    open_hour: int,
    close_hour: int,
    cfg: InstrumentConfig,
) -> bool:
    dt = dt.astimezone(timezone.utc)
    weekday = dt.weekday()
    hour = dt.hour
    break_start = _hour_from_time(cfg.daily_break.start) if cfg.daily_break else close_hour

    if weekday == 5:
        return False
    if weekday == 6 and hour < open_hour:
        return False
    if hour == break_start:
        return False
    if weekday == 4 and hour >= close_hour:
        return False
    return True


def pip_size_for(instrument: Instrument) -> float:
    """Minimum price increment from instruments.yaml."""
    cfg = _instrument_configs().get(instrument)
    if cfg is not None:
        return cfg.pip_size
    return 0.0001


def is_inactive_flat_bar(
    instrument: Instrument,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: float,
) -> bool:
    """Stale zero-/low-activity bars left by feeds during pauses."""
    bar_range = high - low
    pip = pip_size_for(instrument)
    if bar_range <= 0:
        return True
    if volume <= 0 and bar_range <= pip * 2:
        return True
    if open_ == close and bar_range <= pip:
        return True
    return False


def is_chart_bar(
    dt: datetime,
    instrument: Instrument,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: float,
) -> bool:
    """Whether a bar should appear on trading/replay charts."""
    if not is_instrument_session_open(dt, instrument):
        return False
    return not is_inactive_flat_bar(instrument, open_, high, low, close, volume)