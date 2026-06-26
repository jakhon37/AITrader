# 🚀 Quick Start: Paper Trading with Live Data

This guide helps you start real-time paper trading with live dashboards in **one command**.

---

## ⚡ Quick Start (TL;DR)

```bash
# Start everything
./scripts/start_webui.sh

# Check status
./scripts/status_paper.sh

# Stop everything
./scripts/stop_webui.sh
```

Open the trading terminal:
- **Web UI**: http://localhost:5173
- **API / health**: http://localhost:8000/api/health

---

## 📋 Prerequisites

1. **Install dependencies:**
   ```bash
   pip install -e ".[live_data,dashboard]"
   ```

2. **Trained models:**
   ```bash
   # If no models exist, train one:
   python scripts/train_all.py --epochs 10
   ```

3. **Data available:**
   - Live data: Automatically fetched from Yahoo Finance ✅
   - Or use historical: `./scripts/start_webui.sh --no-live`

---

## 🎯 Usage

### Basic Start

```bash
./scripts/start_webui.sh
```

This starts:
- ✅ Paper trading with **live data** ($100k capital, EUR/USD)
- ✅ Paper monitor dashboard (port 8501)
- ✅ Feature explorer dashboard (port 8502)
- ✅ All running in background with logs

### With Options

```bash
# Custom capital and interval
./scripts/start_webui.sh --capital 50000 --interval 1800

# Multiple symbols
./scripts/start_webui.sh --symbols "eurusd gbpusd usdjpy"

# Historical data only (no live)
./scripts/start_webui.sh --no-live
```

**Available Options:**
- `--capital N` - Initial capital (default: $100,000)
- `--symbols "SYM1 SYM2"` - Symbols to trade (default: eurusd)
- `--interval N` - Seconds between trading iterations (default: 3600)
- `--no-live` - Use historical CSV data instead of live

---

## 📊 Monitoring

### Check Status

```bash
./scripts/status_paper.sh
```

**Shows:**
- Service status (running/stopped)
- Process IDs (PIDs)
- Dashboard URLs
- Recent activity
- Trading statistics

### View Logs

```bash
# Paper trading logs
tail -f logs/paper_trading.log

# Monitor dashboard logs
tail -f logs/monitor_dashboard.log

# Feature explorer logs
tail -f logs/feature_explorer.log

# Audit trail (all trades)
tail -f logs/audit.jsonl
```

### Open Dashboards

After starting, open in your browser:

**Paper Monitor** (http://localhost:8501)
- Real-time portfolio value
- Equity curve
- Trade PnL
- Win rate and metrics
- Recent events

**Feature Explorer** (http://localhost:8502)
- Price charts (candlesticks)
- Feature time series
- Correlation heatmap
- Statistical analysis

---

## 🛑 Stopping

### Stop All Services

```bash
./scripts/stop_webui.sh
```

Stops:
- Paper trading process
- Paper monitor dashboard
- Feature explorer dashboard

### Emergency Stop

If `stop_webui.sh` doesn't work:

```bash
# Kill all related processes
pkill -f "run_paper.py"
pkill -f "streamlit run dashboards"
```

---

## 📁 File Structure

After starting, you'll have:

```
trading-platform/
├── logs/
│   ├── paper_trading.log       # Paper trading output
│   ├── monitor_dashboard.log   # Monitor dashboard logs
│   ├── feature_explorer.log    # Explorer logs
│   └── audit.jsonl             # Trade audit trail
├── .paper_trading.pid          # Paper trading PID
├── .monitor_dashboard.pid      # Monitor PID
└── .feature_explorer.pid       # Explorer PID
```

---

## 🔧 Troubleshooting

### Services Not Starting

1. **Check if already running:**
   ```bash
   ./scripts/status_paper.sh
   ```

2. **Stop existing services:**
   ```bash
   ./scripts/stop_webui.sh
   ```

3. **Check logs for errors:**
   ```bash
   tail logs/paper_trading.log
   ```

### Port Already in Use

**Change dashboard ports:**
```bash
# Edit config/instruments.yaml or config/dev.yaml
MONITOR_DASHBOARD_PORT=8503  # Change from 8501
FEATURE_EXPLORER_PORT=8504   # Change from 8502
```

### No Live Data

If Yahoo Finance is down, use historical data:
```bash
./scripts/start_webui.sh --no-live
```

### Model Not Found

Train a model first:
```bash
python scripts/train_all.py --epochs 10
```

---

## 📈 What to Expect

### First 5 Minutes
- Paper trading initializes
- Loads trained model
- Fetches live data
- Dashboards start
- First signal generated

### First Hour
- Multiple trading iterations
- Positions opened/closed
- PnL tracked in dashboard
- Equity curve updates

### First Day
- Continuous trading (every hour by default)
- Multiple trades executed
- Performance metrics calculated
- Audit log growing

### First Week
- System stability validated
- Win rate and Sharpe ratio calculated
- Drawdown monitoring
- Ready for evaluation

---

## 💡 Best Practices

### For Paper Trading

1. **Start small:** Default $100k is fine for testing
2. **Monitor daily:** Check dashboards once per day minimum
3. **Check logs:** Review `paper_trading.log` for errors
4. **Validate trades:** Ensure audit log captures all events
5. **Track metrics:** Win rate, Sharpe ratio, max drawdown

### For Production Readiness

After 4-6 weeks of paper trading:
1. ✅ No crashes or halts
2. ✅ Sharpe ratio > 0.5
3. ✅ Win rate > 45%
4. ✅ Max drawdown < 20%
5. ✅ All events logged correctly
6. ✅ Circuit breaker triggers appropriately

Then review: `docs/go-live-checklist.md`

---

## 🎯 Example Workflow

### Day 1: Start Paper Trading
```bash
# Morning: Start services
./scripts/start_webui.sh

# Check status
./scripts/status_paper.sh

# Open dashboards in browser
# - http://localhost:8501 (monitor)
# - http://localhost:8502 (explorer)

# Evening: Check performance
tail logs/audit.jsonl
```

### Daily: Monitor Performance
```bash
# Check status
./scripts/status_paper.sh

# View recent trades
tail -n 20 logs/audit.jsonl | grep position

# Check dashboard metrics
# - Win rate
# - Total PnL
# - Sharpe ratio
```

### Weekly: Review and Adjust
```bash
# Check full week performance
grep "Final Stats" logs/paper_trading.log

# Review all trades
cat logs/audit.jsonl | grep position_close | wc -l

# If performance poor:
# - Retrain model with more data
# - Adjust risk parameters
# - Check for model drift
```

---

## 🔗 Related Documentation

- **Go-Live Checklist**: `docs/go-live-checklist.md`
- **Dashboard Guide**: `dashboards/README.md`
- **Live Data**: `src/data/loaders/live_data.py`
- **Paper Trading**: `scripts/run_paper.py`

---

## ❓ FAQ

**Q: How long should I run paper trading?**
A: Minimum 4-6 weeks for proper validation.

**Q: Can I trade multiple symbols?**
A: Yes! `./scripts/start_webui.sh --symbols "eurusd gbpusd usdjpy"`

**Q: Is the data really live?**
A: Yes! Fetched from Yahoo Finance in real-time.

**Q: Can I run this 24/7?**
A: Yes, but Forex markets close on weekends (Friday 5pm - Sunday 5pm EST).

**Q: How do I know if it's working?**
A: Check dashboards, logs should show "Using LIVE market data".

**Q: What if I want to pause?**
A: `./scripts/stop_webui.sh` - restart anytime with `./scripts/start_webui.sh`

---

**Ready to start? Run:**
```bash
./scripts/start_webui.sh
```

**Then open:** http://localhost:8501

Happy paper trading! 🚀📈
