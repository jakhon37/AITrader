# AITrader Dashboards

Interactive Streamlit dashboards for monitoring and exploring the AITrader system.

## Dashboards

### 1. Paper Trading Monitor (`paper_monitor.py`)

Real-time monitoring of paper trading performance.

**Features:**
- 📊 Live portfolio value and equity curve
- 💰 Total PnL and return metrics
- 📈 Individual trade PnL visualization
- 📋 Recent events log from audit trail
- 🔄 Auto-refresh every 5 seconds
- 🎯 Win rate and trade statistics

**Usage:**
```bash
streamlit run dashboards/paper_monitor.py
```

**Requirements:**
- Audit log must exist (`logs/audit.jsonl`)
- Paper trading should be running for live updates

---

### 2. Feature Explorer (`feature_explorer.py`)

Interactive exploration of market data and features.

**Features:**
- 📈 Candlestick price charts with volume
- 🔢 Feature time series visualization
- 🔗 Correlation heatmap for feature analysis
- 📊 Statistical summaries (mean, std, missing values)
- 📉 Feature distribution histograms
- 🎛️ Configurable lookback period

**Usage:**
```bash
streamlit run dashboards/feature_explorer.py
```

**Supported Symbols:**
- EUR/USD
- GBP/USD
- USD/JPY
- Gold

---

## Installation

Install dashboard dependencies:
```bash
pip install streamlit streamlit-extras
```

Or install from project dependencies:
```bash
pip install -e ".[dashboard]"
```

---

## Running Dashboards

### Single Dashboard
```bash
# Paper trading monitor
streamlit run dashboards/paper_monitor.py

# Feature explorer
streamlit run dashboards/feature_explorer.py
```

### Custom Port
```bash
streamlit run dashboards/paper_monitor.py --server.port 8502
```

### Disable Auto-refresh
Uncheck "Auto-refresh (5s)" in the sidebar of paper_monitor.py

---

## Dashboard Architecture

```
dashboards/
├── paper_monitor.py      # Real-time paper trading monitoring
├── feature_explorer.py   # Feature and data exploration
└── README.md            # This file
```

**Data Sources:**
- `logs/audit.jsonl` - Audit log for trade events
- `data/raw/*.csv` - Market data files
- `src/features/` - Feature computation modules

**Key Libraries:**
- Streamlit - Dashboard framework
- Plotly - Interactive charts
- Pandas - Data manipulation

---

## Tips

**Paper Monitor:**
- Start paper trading first: `python scripts/run_paper.py`
- Monitor in real-time with auto-refresh enabled
- Check recent events for errors or halts

**Feature Explorer:**
- Use correlation heatmap to find redundant features
- Check distributions for outliers
- Monitor missing value percentages
- Increase lookback for long-term analysis

---

## Future Enhancements

- [ ] Backtest comparison dashboard
- [ ] Model performance analyzer
- [ ] Real-time signal dashboard
- [ ] Risk metrics dashboard
- [ ] Multi-symbol comparison view

---

## Troubleshooting

**Port already in use:**
```bash
streamlit run dashboards/paper_monitor.py --server.port 8502
```

**No data in paper monitor:**
- Check if audit log exists: `ls logs/audit.jsonl`
- Start paper trading: `python scripts/run_paper.py --iterations 1`

**Features not loading:**
- Ensure data files exist: `ls data/raw/*.csv`
- Check feature engine: `pytest tests/unit/test_feature_engine.py`

---

**Last Updated:** 2026-03-06
