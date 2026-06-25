"""Unified report generator for D08-BACKTEST."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
from typing import Any, List, Dict
import uuid

import pandas as pd

from src.core.contracts import Instrument

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
        html_content = self._generate_html_content(report_data)
        with open(html_path, "w") as f:
            f.write(html_content)

        # 4. Enforce Retention Policy
        self._cleanup_old_reports()

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

    def _generate_html_content(self, data: Dict[str, Any]) -> str:
        """Generate self-contained HTML report with modern dark styling and Chart.js."""
        metadata = data["metadata"]
        metrics = data["metrics"]
        
        # Format lists for injection into template Javascript
        timestamps = [pt["timestamp"][:16] for pt in data["equity_curve"]]
        equities = [pt["equity"] for pt in data["equity_curve"]]
        
        # Trades distribution count
        win_count = len([t for t in data["trades"] if t["pnl"] > 0])
        loss_count = len([t for t in data["trades"] if t["pnl"] < 0])

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AITrader Report - {metadata["instrument"]} ({metadata["mode"].upper()})</title>
    <!-- Modern Typography -->
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {{
            --bg-primary: #0b0f19;
            --bg-secondary: #161e31;
            --text-primary: #f3f4f6;
            --text-secondary: #9ca3af;
            --accent-green: #10b981;
            --accent-red: #ef4444;
            --accent-blue: #3b82f6;
            --border-color: #24324f;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            font-family: 'Inter', sans-serif;
            background-color: var(--bg-primary);
            color: var(--text-primary);
            padding: 2rem;
            line-height: 1.5;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}

        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 1.5rem;
            margin-bottom: 2rem;
        }}

        h1 {{
            font-size: 2rem;
            font-weight: 700;
            background: linear-gradient(90deg, #60a5fa, #34d399);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}

        .meta-info {{
            font-size: 0.875rem;
            color: var(--text-secondary);
            text-align: right;
        }}

        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }}

        .card {{
            background-color: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 1.5rem;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
            transition: transform 0.2s, border-color 0.2s;
        }}

        .card:hover {{
            transform: translateY(-2px);
            border-color: var(--accent-blue);
        }}

        .card-label {{
            font-size: 0.875rem;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 0.5rem;
        }}

        .card-value {{
            font-size: 1.75rem;
            font-weight: 700;
        }}

        .positive {{ color: var(--accent-green); }}
        .negative {{ color: var(--accent-red); }}

        .charts-container {{
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 1.5rem;
            margin-bottom: 2rem;
        }}

        @media (max-width: 900px) {{
            .charts-container {{
                grid-template-columns: 1fr;
            }}
        }}

        .table-section {{
            background-color: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 1.5rem;
            overflow-x: auto;
        }}

        .table-title {{
            font-size: 1.25rem;
            font-weight: 600;
            margin-bottom: 1rem;
            border-left: 4px solid var(--accent-blue);
            padding-left: 0.75rem;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.875rem;
            text-align: left;
        }}

        th, td {{
            padding: 0.75rem 1rem;
            border-bottom: 1px solid var(--border-color);
        }}

        th {{
            color: var(--text-secondary);
            font-weight: 600;
            text-transform: uppercase;
            font-size: 0.75rem;
        }}

        tr:hover {{
            background-color: rgba(255, 255, 255, 0.02);
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div>
                <h1>AITrader Performance Report</h1>
                <p style="color: var(--text-secondary);">Mode: {metadata["mode"].upper()} | Instrument: {metadata["instrument"]}</p>
            </div>
            <div class="meta-info">
                <p>Generated: {metadata["generated_at"][:19]} UTC</p>
                <p>Period: {metadata["start_date"][:10]} to {metadata["end_date"][:10]}</p>
            </div>
        </header>

        <div class="metrics-grid">
            <div class="card">
                <div class="card-label">Net Profit</div>
                <div class="card-value {"positive" if metrics.get("net_profit", 0.0) >= 0 else "negative"}">
                    ${metrics.get("net_profit", 0.0):+,.2f} ({metrics.get("net_profit_pct", 0.0):+,.2f}%)
                </div>
            </div>
            <div class="card">
                <div class="card-label">Total Trades</div>
                <div class="card-value">{metrics.get("total_trades", 0)}</div>
            </div>
            <div class="card">
                <div class="card-label">Win Rate</div>
                <div class="card-value" style="color: var(--accent-blue);">{metrics.get("win_rate", 0.0):.2f}%</div>
            </div>
            <div class="card">
                <div class="card-label">Max Drawdown</div>
                <div class="card-value negative">{metrics.get("max_drawdown_pct", metrics.get("max_dd", 0.0)):.2f}%</div>
            </div>
        </div>

        <div class="charts-container">
            <div class="card">
                <div class="table-title">Equity Curve</div>
                <div style="height: 350px;">
                    <canvas id="equityChart"></canvas>
                </div>
            </div>
            <div class="card">
                <div class="table-title">Trade Distribution</div>
                <div style="height: 350px; display: flex; justify-content: center; align-items: center;">
                    <canvas id="distributionChart"></canvas>
                </div>
            </div>
        </div>

        <div class="table-section">
            <div class="table-title">Trade History ({len(data["trades"])} completed)</div>
            <table>
                <thead>
                    <tr>
                        <th>Entry Time</th>
                        <th>Exit Time</th>
                        <th>Side</th>
                        <th>Size</th>
                        <th>Entry Price</th>
                        <th>Exit Price</th>
                        <th>PnL</th>
                        <th>PnL %</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(f'''
                    <tr>
                        <td>{t["entry_time"][:16]}</td>
                        <td>{t["exit_time"][:16]}</td>
                        <td style="color: {"var(--accent-green)" if t["side"] == "long" else "var(--accent-red)"}">{t["side"].upper()}</td>
                        <td>{t["size"]:.2f}</td>
                        <td>{t["entry_price"]:.5f}</td>
                        <td>{t["exit_price"]:.5f}</td>
                        <td class="{"positive" if t["pnl"] >= 0 else "negative"}">${t["pnl"]:+,.2f}</td>
                        <td class="{"positive" if t["pnl"] >= 0 else "negative"}">{t["pnl_pct"]*100.0:+,.2f}%</td>
                    </tr>
                    ''' for t in data["trades"])}
                </tbody>
            </table>
        </div>
    </div>

    <script>
        // Setup Equity Curve Chart
        const equityCtx = document.getElementById('equityChart').getContext('2d');
        const timestamps = {json.dumps(timestamps)};
        const equities = {json.dumps(equities)};
        
        new Chart(equityCtx, {{
            type: 'line',
            data: {{
                labels: timestamps,
                datasets: [{{
                    label: 'Portfolio Equity ($)',
                    data: equities,
                    borderColor: '#3b82f6',
                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.1,
                    pointRadius: 0
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{ display: false }}
                }},
                scales: {{
                    x: {{
                        grid: {{ color: '#24324f' }},
                        ticks: {{ color: '#9ca3af' }}
                    }},
                    y: {{
                        grid: {{ color: '#24324f' }},
                        ticks: {{ color: '#9ca3af' }}
                    }}
                }}
            }}
        }});

        // Setup Trade Distribution Chart
        const distCtx = document.getElementById('distributionChart').getContext('2d');
        new Chart(distCtx, {{
            type: 'doughnut',
            data: {{
                labels: ['Wins', 'Losses'],
                datasets: [{{
                    data: [{win_count}, {loss_count}],
                    backgroundColor: ['#10b981', '#ef4444'],
                    borderColor: '#161e31',
                    borderWidth: 2
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{
                        position: 'bottom',
                        labels: {{ color: '#f3f4f6' }}
                    }}
                }}
            }}
        }});
    </script>
</body>
</html>
"""
        return html

    def _cleanup_old_reports(self) -> None:
        """Enforce report storage limits."""
        # Clean by age
        cutoff_date = datetime.now() - timedelta(days=self.retention_days)
        
        # Read files in reports directory
        files = list(self.reports_dir.glob("*.*"))
        for f in files:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if mtime < cutoff_date:
                try:
                    f.unlink()
                except Exception as e:
                    logger.warning(f"Failed to delete old report {f.name}: {e}")

        # Re-list after age cleanup, and clean by total count
        files = []
        for ext in [".json", ".html"]:
            files.extend(list(self.reports_dir.glob(f"*{ext}")))
            
        # Sort by creation time (oldest first)
        files.sort(key=lambda x: x.stat().st_mtime)
        
        # We enforce retention_count per file type or total.
        # Let's enforce it per file type to make sure we don't delete matching HTML/JSON sets unequally.
        for ext in [".json", ".html"]:
            type_files = [f for f in files if f.suffix == ext]
            if len(type_files) > self.retention_count:
                to_delete = type_files[:len(type_files) - self.retention_count]
                for f in to_delete:
                    try:
                        f.unlink()
                    except Exception as e:
                        logger.warning(f"Failed to delete report {f.name} for limit: {e}")
