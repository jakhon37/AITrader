"""Performance scorer for manual replay sessions."""

from __future__ import annotations

from typing import Any, List, Dict
import numpy as np
import pandas as pd

from src.core.contracts import Order, OrderSide, OrderStatus


class ReplayScorer:
    """Calculates manual replay performance metrics and grades."""

    @staticmethod
    def calculate_metrics(
        trades: List[Any],
        equity_curve: pd.Series,
        initial_capital: float,
        buy_and_hold_return: float = 0.0,
        model_metrics: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Generate a complete performance scorecard."""
        final_equity = float(equity_curve.iloc[-1]) if not equity_curve.empty else initial_capital
        net_profit = final_equity - initial_capital
        net_profit_pct = (net_profit / initial_capital) * 100.0

        # Parse trades list (which can contain Trade objects, dictionaries, or Order objects) into standard dicts

        # Since we might have completed trade objects (similar to Trade class in engine.py),
        # let's accept either Order objects or list of Trade objects/dicts.
        # Let's normalize inputs to support both.
        trade_records: List[Dict[str, Any]] = []
        for t in trades:
            if hasattr(t, "pnl"):
                trade_records.append({
                    "pnl": getattr(t, "pnl"),
                    "side": getattr(t, "side"),
                    "commission": getattr(t, "commission", 0.0),
                    "sl": getattr(t, "sl", None),
                    "tp": getattr(t, "tp", None),
                    "entry_price": getattr(t, "entry_price", 0.0),
                    "exit_price": getattr(t, "exit_price", 0.0),
                })
            elif isinstance(t, dict):
                trade_records.append(t)

        total_trades = len(trade_records)
        wins = [t for t in trade_records if t["pnl"] > 0]
        losses = [t for t in trade_records if t["pnl"] < 0]
        
        win_rate = (len(wins) / total_trades * 100.0) if total_trades > 0 else 0.0
        
        gross_profit = sum(t["pnl"] for t in wins)
        gross_loss = abs(sum(t["pnl"] for t in losses))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf") if gross_profit > 0 else 1.0

        # Average Risk-to-Reward (R:R) ratio estimation
        avg_win = (gross_profit / len(wins)) if len(wins) > 0 else 0.0
        avg_loss = (gross_loss / len(losses)) if len(losses) > 0 else 0.0
        avg_rr = (avg_win / avg_loss) if avg_loss > 0 else float("inf") if avg_win > 0 else 0.0

        # Max Drawdown
        if not equity_curve.empty:
            rolling_max = equity_curve.cummax()
            drawdowns = (equity_curve - rolling_max) / rolling_max
            max_dd = float(drawdowns.min() * 100.0)
        else:
            max_dd = 0.0

        # Sharpe ratio
        returns = equity_curve.pct_change().dropna()
        if len(returns) > 1 and returns.std() > 0:
            sharpe = float((returns.mean() / returns.std()) * np.sqrt(252))
        else:
            sharpe = 0.0

        # Discipline Score (0 to 100)
        # Check if the user respected their stop loss levels.
        # If exit_price is worse than SL, it means they moved/removed SL or held past SL.
        discipline_violations = 0
        valued_trades_with_sl = 0

        for t in trade_records:
            sl = t.get("sl")
            entry = t.get("entry_price", 0.0)
            exit_p = t.get("exit_price", 0.0)
            side = t.get("side")

            if sl is not None and sl > 0:
                valued_trades_with_sl += 1
                if side in ["long", "buy", OrderSide.BUY]:
                    # For long, exit price should be >= SL. If exit is below SL (accounting for tiny slippage), it's a violation
                    if exit_p < sl - (entry * 0.0001):
                        discipline_violations += 1
                elif side in ["short", "sell", OrderSide.SELL]:
                    # For short, exit price should be <= SL.
                    if exit_p > sl + (entry * 0.0001):
                        discipline_violations += 1

        if valued_trades_with_sl > 0:
            discipline_score = ((valued_trades_with_sl - discipline_violations) / valued_trades_with_sl) * 100.0
        else:
            # Default to 100 if no SL was set (or 50 if they traded completely without SL as a penalty)
            discipline_score = 100.0 if total_trades == 0 else 50.0

        scorecard = {
            "initial_capital": initial_capital,
            "final_equity": final_equity,
            "net_profit": net_profit,
            "net_profit_pct": net_profit_pct,
            "total_trades": total_trades,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "average_rr": avg_rr,
            "max_drawdown_pct": max_dd,
            "sharpe_ratio": sharpe,
            "discipline_score": discipline_score,
            "buy_and_hold_return_pct": buy_and_hold_return * 100.0,
            "outperformed_benchmark": net_profit_pct > (buy_and_hold_return * 100.0),
        }

        if model_metrics:
            scorecard["model_comparison"] = {
                "model_net_profit_pct": model_metrics.get("net_profit_pct", 0.0),
                "model_win_rate": model_metrics.get("win_rate", 0.0),
                "model_profit_factor": model_metrics.get("profit_factor", 1.0),
                "user_outperformed_model": net_profit_pct > model_metrics.get("net_profit_pct", 0.0),
            }

        return scorecard
