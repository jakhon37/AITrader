# Visualization & Monitoring Roadmap

**Purpose:** Comprehensive plan for visualization and monitoring capabilities across all development phases.

---

## 🎯 Overview

The platform will have **3 tiers** of visualization:

1. **Static Plots** (Phase 4) - Backtesting analysis
2. **Interactive Dashboard** (Phase 6) - Paper/live trading monitoring  
3. **Production Dashboard** (Phase 7, Optional) - Enterprise-grade monitoring

---

## 📊 Phase 4: Static Visualization (Backtesting)

### Tech Stack
- **matplotlib** - Core plotting
- **plotly** - Interactive HTML exports
- **seaborn** - Statistical plots
- **mplfinance** - Candlestick charts

### File Structure
```
src/visualization/
├── __init__.py
├── backtest_plots.py      # Equity curve, drawdown, returns
├── trade_plots.py         # Entry/exit markers, P&L per trade
├── metrics_plots.py       # Performance metrics grid
├── feature_plots.py       # Feature distributions, correlations
├── regime_plots.py        # Regime overlay on price chart
└── report_generator.py    # Combine all plots into HTML/PDF
```

### Key Visualizations

#### 1. Equity Curve
- Cumulative returns over time
- Compare to buy-and-hold benchmark
- Mark major drawdown periods
- **Output:** `equity_curve.png`, 1200x600px

#### 2. Drawdown Chart
- Underwater equity curve
- Highlight max drawdown period
- Recovery time annotations
- **Output:** `drawdown.png`, 1200x600px

#### 3. Trade Markers on Price Chart
- Candlestick chart with OHLC
- Green ▲ for longs, Red ▼ for shorts
- Background color for regime (trending/ranging/volatile)
- Moving averages overlay
- **Output:** `trades_on_chart.png`, 1600x800px

#### 4. Returns Distribution
- Histogram of daily returns
- Normal distribution overlay
- Statistics box (mean, std, skew, kurtosis)
- **Output:** `returns_dist.png`, 800x600px

#### 5. Monthly Returns Heatmap
- Calendar-style heatmap
- Green for positive months, red for negative
- Yearly totals
- **Output:** `monthly_returns.png`, 1000x400px

#### 6. Performance Metrics Grid
- 2x3 grid of key metrics:
  - Sharpe Ratio
  - Max Drawdown
  - Win Rate
  - Avg Profit per Trade
  - Total Trades
  - Profit Factor
- **Output:** `metrics_summary.png`, 1200x800px

#### 7. Rolling Sharpe Ratio
- 60-day rolling Sharpe
- Threshold line at 1.0
- Identify performance degradation periods
- **Output:** `rolling_sharpe.png`, 1200x400px

#### 8. Trade Analysis
- Win rate by hour/day/month
- Avg profit vs loss
- Hold time distribution
- **Output:** `trade_analysis.png`, 1200x800px

#### 9. Feature Importance
- Bar chart of top 20 features
- Permutation importance or SHAP values
- **Output:** `feature_importance.png`, 800x1000px

#### 10. Regime Overlay
- Price chart with colored background zones
- Regime state labels
- Regime transition markers
- **Output:** `regime_overlay.png`, 1600x600px

### Report Generator

**Function:**
```python
def generate_backtest_report(
    results: BacktestResults,
    output_dir: str = "reports/",
    format: str = "html",  # or "pdf", "png_only"
) -> str:
    """Generate comprehensive backtest report.
    
    Returns:
        Path to generated report
    """
```

**Output Structure:**
```
reports/backtest_2026_03_06_142530/
├── equity_curve.png
├── drawdown.png
├── trades_on_chart.png
├── returns_dist.png
├── monthly_returns.png
├── metrics_summary.png
├── rolling_sharpe.png
├── trade_analysis.png
├── feature_importance.png
├── regime_overlay.png
├── summary_stats.json
└── full_report.html      # All plots + narrative
```

**HTML Report Sections:**
1. Executive Summary (key metrics)
2. Performance Overview (equity + drawdown)
3. Trade Analysis (markers + stats)
4. Risk Metrics (Sharpe, VaR, etc.)
5. Feature Analysis (importance + correlations)
6. Appendix (raw data tables)

### Usage Example

```python
from src.backtest.runner import run_backtest
from src.visualization.report_generator import generate_backtest_report

# Run backtest
results = run_backtest(
    config="config/backtest.yaml",
    start_date="2024-01-01",
    end_date="2025-12-31"
)

# Generate report
report_path = generate_backtest_report(
    results,
    output_dir="reports/",
    format="html"
)

print(f"Report saved to: {report_path}")
# Open in browser
import webbrowser
webbrowser.open(report_path)
```

### Success Criteria
- [ ] All 10 visualizations implemented
- [ ] Report generator creates HTML with all plots
- [ ] PNG exports work for presentations
- [ ] Plots are publication-quality (high DPI, clear labels)
- [ ] Report generation takes < 5 seconds

---

## 📱 Phase 6: Interactive Dashboard (Paper Trading)

### Tech Stack
- **Streamlit** - Dashboard framework
- **Plotly** - Interactive charts
- **streamlit-extras** - Additional widgets

### File Structure
```
dashboards/
├── paper_monitor.py       # Main paper trading dashboard
├── feature_explorer.py    # Feature analysis tool
├── backtest_analyzer.py   # Compare backtest configs
└── components/
    ├── metrics_card.py    # Reusable metric display
    ├── trade_table.py     # Trade log component
    └── chart_panel.py     # Chart components
```

### Paper Trading Monitor (`dashboards/paper_monitor.py`)

**Features:**

1. **Header Section**
   - Current P&L (daily, weekly, total)
   - Account balance
   - Open positions count
   - Last update timestamp

2. **Real-Time Charts**
   - Live equity curve (updates every minute)
   - Intraday P&L
   - Current positions on price chart

3. **Positions Table**
   - Symbol, Entry Price, Current Price, P&L, Duration
   - Click row to see detail modal

4. **Recent Trades Log**
   - Last 50 trades
   - Filter by symbol, direction, outcome
   - Export to CSV

5. **Performance Metrics**
   - Rolling Sharpe (1d, 7d, 30d)
   - Win rate
   - Avg profit/loss
   - Max drawdown

6. **Feature Monitor**
   - Current feature values
   - Feature distribution plots
   - Regime indicator (colored badge)

7. **Alerts Panel**
   - Drawdown warnings
   - Unusual feature values
   - Circuit breaker status

**Layout:**
```
+----------------------------------------------------------+
|  Paper Trading Monitor          [Refresh] [Settings]     |
+----------------------------------------------------------+
| P&L: $1,234  | Win Rate: 52% | Open: 2 | Updated: 10:30 |
+----------------------------------------------------------+
|                                                           |
|              [Live Equity Curve Chart]                    |
|                                                           |
+----------------------------------------------------------+
| Open Positions          | Recent Trades                   |
| Symbol | Entry | P&L    | Time  | Symbol | P&L          |
| EURUSD | 1.05  | +$50   | 10:25 | GBPUSD | +$30         |
+----------------------------------------------------------+
| Performance Metrics     | Feature Monitor                 |
| Sharpe: 1.5             | RSI_14: 65                     |
| Max DD: -3.2%           | Regime: Bullish                |
+----------------------------------------------------------+
```

**Auto-Refresh:**
- Metrics update every 60 seconds
- Charts update every 5 minutes
- Trade log updates on new trades

**Deployment:**
```bash
# Run locally
streamlit run dashboards/paper_monitor.py --server.port 8501

# Access at http://localhost:8501
```

### Feature Explorer (`dashboards/feature_explorer.py`)

**Purpose:** Analyze feature behavior and distributions

**Features:**
1. Upload OHLCV data
2. Select features to analyze
3. View distributions (histogram + KDE)
4. Correlation heatmap
5. Feature importance over time
6. Regime-specific feature stats

### Backtest Analyzer (`dashboards/backtest_analyzer.py`)

**Purpose:** Compare different backtest configurations

**Features:**
1. Load multiple backtest results
2. Side-by-side metrics comparison
3. Equity curve overlay
4. Parameter sensitivity analysis
5. Export comparison report

### Success Criteria
- [ ] Paper monitor runs without errors
- [ ] Auto-refresh works reliably
- [ ] Dashboard loads in < 3 seconds
- [ ] Mobile-friendly layout
- [ ] Can run for days without restart

---

## 🚀 Phase 7: Production Dashboard (Optional)

### Tech Stack
- **FastAPI** - Backend API
- **React + TypeScript** - Frontend
- **Plotly.js** - Client-side charts
- **WebSocket** - Real-time updates
- **PostgreSQL** - Metrics storage

### Architecture
```
┌─────────────┐      WebSocket      ┌──────────────┐
│  React UI   │◄─────────────────────│  FastAPI     │
│  (Browser)  │                      │  Backend     │
│             │      REST API        │              │
│             │◄─────────────────────│              │
└─────────────┘                      └──────┬───────┘
                                            │
                                            │
                                      ┌─────▼──────┐
                                      │ PostgreSQL │
                                      │  (Metrics) │
                                      └────────────┘
```

### Features (Enterprise-Grade)
- Multi-user authentication
- Role-based access control
- Historical data retention
- Custom alerting rules
- Mobile app support
- Audit trail
- Export to PDF/Excel
- Compliance reporting

### When to Build
**Only if needed for:**
- Multiple users/teams
- Regulatory compliance
- 24/7 monitoring requirement
- Mobile access critical

**Alternative:** Continue using Streamlit (good enough for solo trader)

---

## 📦 Dependencies

```toml
[project.optional-dependencies]
viz = [
  "matplotlib>=3.7",
  "plotly>=5.0",
  "seaborn>=0.12",
  "mplfinance>=0.12",
]

dashboard = [
  "streamlit>=1.30",
  "streamlit-extras>=0.3",
  "watchdog>=3.0",  # File monitoring
]

# Optional for Phase 7
production = [
  "fastapi>=0.100",
  "uvicorn>=0.23",
  "websockets>=11.0",
  "sqlalchemy>=2.0",
  "psycopg2-binary>=2.9",
]
```

---

## 🎨 Design Guidelines

### Color Scheme
- **Profit:** #00C853 (Green)
- **Loss:** #FF5252 (Red)
- **Neutral:** #2196F3 (Blue)
- **Warning:** #FFC107 (Amber)
- **Background:** #FAFAFA (Light Gray)

### Chart Style
- Clean, minimal design
- High contrast for readability
- Consistent font sizes (12pt body, 14pt titles)
- Grid lines subtle (light gray)
- Export at 300 DPI for print

### Accessibility
- Color-blind friendly palettes
- Text labels in addition to colors
- Keyboard navigation support
- Screen reader compatibility

---

## 📊 Metrics to Track

### Performance Metrics
- Total Return
- Sharpe Ratio
- Sortino Ratio
- Max Drawdown
- Recovery Time
- Calmar Ratio
- Win Rate
- Profit Factor
- Avg Profit/Loss
- Trade Frequency

### Risk Metrics
- VaR (95%, 99%)
- CVaR
- Beta (vs SPY)
- Correlation to benchmarks
- Daily volatility

### Operational Metrics
- Uptime
- API latency
- Order fill rate
- Slippage
- Commission costs

---

## 🚦 Monitoring Alerts

### Critical (Red)
- Drawdown > 10%
- Circuit breaker triggered
- API connection lost
- Model prediction failed

### Warning (Yellow)
- Drawdown > 5%
- Win rate < 45% (rolling 20 trades)
- Unusual feature values (3σ outlier)
- High slippage

### Info (Blue)
- Daily report ready
- New trade executed
- Model retrained
- Config updated

---

## ✅ Testing Plan

### Static Plots (Phase 4)
- [ ] Unit tests for each plot function
- [ ] Verify PNG output dimensions
- [ ] Check plot with edge cases (empty data, single trade)
- [ ] HTML report renders correctly
- [ ] All links work

### Dashboard (Phase 6)
- [ ] Load test (1000 trades, 100 features)
- [ ] Memory leak check (24hr run)
- [ ] Browser compatibility (Chrome, Firefox, Safari)
- [ ] Mobile responsiveness
- [ ] Auto-refresh reliability

---

**Last Updated:** 2026-03-06
**Next Review:** After Phase 3 completion
