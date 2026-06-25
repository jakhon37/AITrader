"""HTML report generator for backtest results."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from backtest.engine import BacktestResult
from backtest.metrics import PerformanceMetrics

logger = logging.getLogger(__name__)


def generate_html_report(
    result: BacktestResult,
    metrics: PerformanceMetrics,
    model_name: str,
    symbol: str,
    plot_files: Optional[dict[str, Path]] = None,
    output_path: Optional[Path] = None,
) -> Path:
    """Generate comprehensive HTML report.

    Args:
        result: BacktestResult
        metrics: PerformanceMetrics
        model_name: Name of the model
        symbol: Trading symbol
        plot_files: Dictionary of plot names to file paths
        output_path: Path to save HTML (default: reports/report_{timestamp}.html)

    Returns:
        Path to generated HTML file
    """
    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = Path("reports") / f"backtest_report_{timestamp}.html"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Generate HTML
    html = _generate_html_content(result, metrics, model_name, symbol, plot_files)

    # Write to file
    with open(output_path, "w") as f:
        f.write(html)

    logger.info(f"Generated HTML report: {output_path}")
    return output_path


def _generate_html_content(
    result: BacktestResult,
    metrics: PerformanceMetrics,
    model_name: str,
    symbol: str,
    plot_files: Optional[dict[str, Path]] = None,
) -> str:
    """Generate HTML content."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Backtest Report: {model_name} on {symbol.upper()}</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
               line-height: 1.6; padding: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; 
                     padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; margin-bottom: 30px; }}
        h2 {{ color: #34495e; margin-top: 30px; margin-bottom: 15px; 
             border-left: 4px solid #3498db; padding-left: 15px; }}
        .meta {{ background: #ecf0f1; padding: 15px; border-radius: 5px; margin-bottom: 30px; }}
        .meta-item {{ display: inline-block; margin-right: 30px; }}
        .meta-label {{ font-weight: bold; color: #7f8c8d; }}
        
        .metrics-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); 
                        gap: 20px; margin: 20px 0; }}
        .metric-card {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                       color: white; padding: 20px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
        .metric-card.green {{ background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); }}
        .metric-card.red {{ background: linear-gradient(135deg, #eb3349 0%, #f45c43 100%); }}
        .metric-card.blue {{ background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); }}
        .metric-label {{ font-size: 0.9em; opacity: 0.9; margin-bottom: 5px; }}
        .metric-value {{ font-size: 2em; font-weight: bold; }}
        
        .plot-container {{ margin: 30px 0; }}
        .plot-container img {{ width: 100%; border-radius: 8px; 
                              box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
        
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #3498db; color: white; font-weight: bold; }}
        tr:hover {{ background: #f5f5f5; }}
        
        .positive {{ color: #27ae60; font-weight: bold; }}
        .negative {{ color: #e74c3c; font-weight: bold; }}
        
        .footer {{ margin-top: 40px; padding-top: 20px; border-top: 2px solid #ecf0f1; 
                  text-align: center; color: #7f8c8d; font-size: 0.9em; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Backtest Report: {model_name} on {symbol.upper()}</h1>
        
        <div class="meta">
            <div class="meta-item">
                <span class="meta-label">Generated:</span> {timestamp}
            </div>
            <div class="meta-item">
                <span class="meta-label">Model:</span> {model_name}
            </div>
            <div class="meta-item">
                <span class="meta-label">Symbol:</span> {symbol.upper()}
            </div>
            <div class="meta-item">
                <span class="meta-label">Period:</span> {result.metadata['start_date'].date()} to {result.metadata['end_date'].date()}
            </div>
        </div>
        
        <h2>📈 Key Metrics</h2>
        <div class="metrics-grid">
            <div class="metric-card {'green' if metrics.total_return > 0 else 'red'}">
                <div class="metric-label">Total Return</div>
                <div class="metric-value">{metrics.total_return:.2%}</div>
            </div>
            <div class="metric-card blue">
                <div class="metric-label">Sharpe Ratio</div>
                <div class="metric-value">{metrics.sharpe_ratio:.2f}</div>
            </div>
            <div class="metric-card red">
                <div class="metric-label">Max Drawdown</div>
                <div class="metric-value">{metrics.max_drawdown:.2%}</div>
            </div>
            <div class="metric-card green">
                <div class="metric-label">Win Rate</div>
                <div class="metric-value">{metrics.win_rate:.1%}</div>
            </div>
        </div>
        
        <h2>💰 Returns & Risk</h2>
        <table>
            <tr><th>Metric</th><th>Value</th></tr>
            <tr><td>Total Return</td><td class="{'positive' if metrics.total_return > 0 else 'negative'}">{metrics.total_return:.2%}</td></tr>
            <tr><td>Annualized Return</td><td>{metrics.annualized_return:.2%}</td></tr>
            <tr><td>Volatility (Annual)</td><td>{metrics.volatility:.2%}</td></tr>
            <tr><td>Downside Deviation</td><td>{metrics.downside_deviation:.2%}</td></tr>
            <tr><td>Sharpe Ratio</td><td>{metrics.sharpe_ratio:.2f}</td></tr>
            <tr><td>Sortino Ratio</td><td>{metrics.sortino_ratio:.2f}</td></tr>
            <tr><td>Calmar Ratio</td><td>{metrics.calmar_ratio:.2f}</td></tr>
        </table>
        
        <h2>📉 Drawdown Analysis</h2>
        <table>
            <tr><th>Metric</th><th>Value</th></tr>
            <tr><td>Max Drawdown</td><td class="negative">{metrics.max_drawdown:.2%}</td></tr>
            <tr><td>Max Drawdown Duration</td><td>{metrics.max_drawdown_duration} days</td></tr>
            <tr><td>Average Drawdown</td><td>{metrics.avg_drawdown:.2%}</td></tr>
        </table>
        
        <h2>🔄 Trade Statistics</h2>
        <table>
            <tr><th>Metric</th><th>Value</th></tr>
            <tr><td>Total Trades</td><td>{metrics.total_trades}</td></tr>
            <tr><td>Win Rate</td><td class="{'positive' if metrics.win_rate > 0.5 else ''}">{metrics.win_rate:.2%}</td></tr>
            <tr><td>Profit Factor</td><td>{metrics.profit_factor:.2f}</td></tr>
            <tr><td>Average Trade</td><td class="{'positive' if metrics.avg_trade > 0 else 'negative'}">${metrics.avg_trade:.2f}</td></tr>
            <tr><td>Average Win</td><td class="positive">${metrics.avg_win:.2f}</td></tr>
            <tr><td>Average Loss</td><td class="negative">${metrics.avg_loss:.2f}</td></tr>
            <tr><td>Best Trade</td><td class="positive">${metrics.best_trade:.2f}</td></tr>
            <tr><td>Worst Trade</td><td class="negative">${metrics.worst_trade:.2f}</td></tr>
            <tr><td>Average Holding Period</td><td>{metrics.avg_holding_period:.1f} days</td></tr>
            <tr><td>Total Commission</td><td>${metrics.total_commission:.2f}</td></tr>
        </table>
"""

    # Add plots if provided
    if plot_files:
        html += "\n        <h2>📊 Visualizations</h2>\n"

        plot_order = [
            "equity_curve",
            "drawdown",
            "returns_dist",
            "monthly_heatmap",
            "trade_analysis",
        ]

        for plot_name in plot_order:
            if plot_name in plot_files:
                plot_path = plot_files[plot_name]
                if plot_path.exists():
                    # Use relative path for embedded images
                    rel_path = plot_path.name
                    html += f"""
        <div class="plot-container">
            <h3>{plot_name.replace('_', ' ').title()}</h3>
            <img src="{rel_path}" alt="{plot_name}">
        </div>
"""

    # Footer
    html += f"""
        <div class="footer">
            <p>Generated by AITrader Backtesting Engine</p>
            <p>Report Date: {timestamp}</p>
        </div>
    </div>
</body>
</html>
"""

    return html
