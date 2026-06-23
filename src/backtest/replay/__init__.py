"""Replay package — public API.

All existing imports continue to work unchanged::

    from src.backtest.replay import StrategyReplaySession, ManualReplaySession

Internal layout
---------------
_utils.py   — get_buffer_duration() helper
_base.py    — BaseReplaySession (shared init, controls, chunk-loader, TF switch)
strategy/   — StrategyReplaySession (watch mode)
manual/     — ManualReplaySession  (trader-training mode)
"""
from src.backtest.replay.strategy import StrategyReplaySession
from src.backtest.replay.manual import ManualReplaySession

__all__ = ["StrategyReplaySession", "ManualReplaySession"]
