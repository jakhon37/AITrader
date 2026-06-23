"""Unified report generator base class for D08-BACKTEST."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from src.core.contracts import Instrument
from src.backtest.reporter.html import generate_html_content
from src.backtest.reporter.cleanup import cleanup_old_reports

logger = logging.getLogger(__name__)


class ReplayReporter:
    """Generates JSON, console summaries, and HTML reports for backtests."""

    def __init__(
        self,
        reports_dir: str = "data/reports",
        retention_count: int = 50,
        retention_days: int = 30,
    ) -> None:
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.retention_count = retention_count
        self.retention_days = retention_days

    def generate(
        self,
        mode: str,
        instrument: Instrument,
        start_date: datetime,
        end_date: datetime,
        metrics: Dict[str, Any],
        trades: List[Dict[str, Any]],
        equity_curve: pd.Series,
    ) -> Dict[str, Path]:
        """Generate JSON and HTML reports, and log a console summary."""
        report_uuid = str(uuid.uuid4())[:8]
        start_str = start_date.strftime("%Y%m%d")
        end_str = end_date.strftime("%Y%m%d")
        filename_base = f"{mode}_{instrument.value}_{start_str}_{end_str}_{report_uuid}"

        # 1. Console Summary Table
        self._print_console_summary(mode, instrument, start_date, end_date, metrics)

        # Create serializable trade records
        serializable_trades = []
        for t in trades:
            trade_dict = {}
            for k, v in t.items():
                if isinstance(v, (datetime, pd.Timestamp)):
                    trade_dict[k] = v.isoformat()
                else:
                    trade_dict[k] = v
            serializable_trades.append(trade_dict)

        # Create serializable equity curve
        serializable_equity = [
            {"timestamp": ts.isoformat(), "equity": float(val)}
            for ts, val in equity_curve.items()
        ]

        report_data = {
            "metadata": {
                "uuid": report_uuid,
                "mode": mode,
                "instrument": instrument.value,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
            "metrics": metrics,
            "trades": serializable_trades,
            "equity_curve": serializable_equity,
        }

        # 2. Write JSON Report
        json_path = self.reports_dir / f"{filename_base}.json"
        with open(json_path, "w") as f:
            json.dump(report_data, f, indent=2)

        # 3. Write HTML Report
        html_path = self.reports_dir / f"{filename_base}.html"
        html_content = generate_html_content(report_data)
        with open(html_path, "w") as f:
            f.write(html_content)

        # 4. Enforce Retention Policy
        cleanup_old_reports(self.reports_dir, self.retention_days, self.retention_count)

        return {"json": json_path, "html": html_path}

    def _print_console_summary(
        self,
        mode: str,
        instrument: Instrument,
        start_date: datetime,
        end_date: datetime,
        metrics: Dict[str, Any],
    ) -> None:
        """Print a structured performance table to stdout."""
        print("\n" + "=" * 60)
        print(f"               AITRADER PERFORMANCE REPORT ({mode.upper()})")
        print(f" Instrument: {instrument.value:<20} Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
        print("=" * 60)
        print(f" Final Equity:          ${metrics.get('final_equity', 0.0):,.2f}")
        print(f" Net Profit:            ${metrics.get('net_profit', 0.0):+,.2f} ({metrics.get('net_profit_pct', 0.0):+,.2f}%)")
        print(f" Total Trades:          {metrics.get('total_trades', 0)}")
        print(f" Win Rate:              {metrics.get('win_rate', 0.0):.2f}%")
        print(f" Profit Factor:         {metrics.get('profit_factor', 0.0):.2f}")
        
        if "average_rr" in metrics:
            print(f" Avg Risk:Reward:       {metrics.get('average_rr', 0.0):.2f}")
        if "sharpe_ratio" in metrics:
            print(f" Sharpe Ratio:          {metrics.get('sharpe_ratio', 0.0):.2f}")
        if "max_drawdown_pct" in metrics:
            print(f" Max Drawdown:          {metrics.get('max_drawdown_pct', 0.0):.2f}%")
        elif "max_dd" in metrics:
            print(f" Max Drawdown:          {metrics.get('max_dd', 0.0):.2f}%")
            
        if "discipline_score" in metrics:
            print(f" Discipline Score:      {metrics.get('discipline_score', 0.0):.1f}/100")
            
        print("=" * 60 + "\n")
