"""Strategy replay sub-package.

Public API::

    from src.backtest.replay.strategy import StrategyReplaySession

Internal layout
---------------
session.py  — StrategyReplaySession class + lifecycle (start / stop / jump_to)
loop.py     — StrategyLoopMixin: the speed-controlled pipeline drive loop
              (swap this file to add event-driven / multi-instrument loop modes)
"""
from src.backtest.replay.strategy.session import StrategyReplaySession

__all__ = ["StrategyReplaySession"]
