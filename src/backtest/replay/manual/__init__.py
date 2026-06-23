"""Manual replay sub-package.

Public API::

    from src.backtest.replay.manual import ManualReplaySession

Internal layout
---------------
session.py   — ManualReplaySession: __init__, resume, start, end_session
stepping.py  — SteppingMixin: step, step_multiple, _replay_loop, _update_session_state
               (add step_back, fast_forward_to, playback_rate_ramp here)
trading.py   — TradingMixin: place_order, close_position
               (add partial_close, modify_sl_tp, bracket_order here)
"""
from src.backtest.replay.manual.session import ManualReplaySession

__all__ = ["ManualReplaySession"]
