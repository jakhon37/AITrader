"""HTML report template generator for D08-BACKTEST."""

from __future__ import annotations

import json
from typing import Any, Dict


def generate_html_content(data: Dict[str, Any]) -> str:
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
