# Multi-Timeframe Trading Guide

AITrader supports multiple timeframes for data analysis and trading, from 1-minute scalping to monthly position trading.

## Supported Timeframes

| Timeframe | Code | Description | Data Lookback Limit | Use Case |
|-----------|------|-------------|---------------------|----------|
| **1 minute** | `1m` | 1-minute bars | 60 days (yfinance limit) | High-frequency scalping |
| **2 minutes** | `2m` | 2-minute bars | 60 days | Fast scalping |
| **5 minutes** | `5m` | 5-minute bars | 60 days | Intraday scalping |
| **15 minutes** | `15m` | 15-minute bars | 60 days | Intraday trading |
| **30 minutes** | `30m` | 30-minute bars | 60 days | Short-term intraday |
| **1 hour** | `1h` | 1-hour bars | 60 days | Swing intraday |
| **4 hours** | `4h` | 4-hour bars | 60 days (resampled from 1h) | Position intraday |
| **1 day** | `1d` | Daily bars | Unlimited | Swing/position trading (default) |
| **1 week** | `1w` | Weekly bars | Unlimited | Long-term position |
| **1 month** | `1mo` | Monthly bars | Unlimited | Very long-term |

## Quick Start

### Using Native Scripts

```bash
# 5-minute scalping
./scripts/start_paper.sh --timeframe 5m --interval 300

# 1-hour swing trading
./scripts/start_paper.sh --timeframe 1h --interval 3600

# 4-hour position trading
./scripts/start_paper.sh --timeframe 4h --interval 14400

# Daily analysis (default)
./scripts/start_paper.sh --timeframe 1d --interval 3600
```

### Using Python Directly

```bash
# 15-minute intraday trading
python scripts/run_paper.py \
    --timeframe 15m \
    --interval 900 \
    --capital 100000 \
    --symbols eurusd

# Multiple symbols, 1-hour timeframe
python scripts/run_paper.py \
    --timeframe 1h \
    --interval 3600 \
    --symbols eurusd gbpusd usdjpy
```

### Using Docker

```bash
# Edit docker-compose.yml to add timeframe
services:
  paper-trading:
    command: >
      python scripts/run_paper.py
      --timeframe 5m
      --interval 300
      --capital 100000

# Then start
./docker/start_docker.sh
```

## Timeframe Selection Guidelines

### 1-Minute to 5-Minute (High-Frequency Scalping)
**Pros:**
- Maximum trading opportunities
- Quick feedback on strategies
- Capture micro-movements

**Cons:**
- High noise-to-signal ratio
- Requires very fast execution
- More commissions/slippage
- Limited to 60 days historical data
- Mentally demanding

**Recommended for:**
- Experienced traders
- High-frequency algorithms
- Markets with tight spreads (Forex majors)

**Interval suggestions:**
- 1m timeframe → 60s interval (check every minute)
- 5m timeframe → 300s interval (check every 5 minutes)

---

### 15-Minute to 1-Hour (Intraday Trading)
**Pros:**
- Good balance of signal quality and opportunities
- Enough data for reliable patterns
- Manageable execution speed
- Still intraday (close before market close)

**Cons:**
- Still limited to 60 days historical
- Requires active monitoring
- Can miss longer trends

**Recommended for:**
- Active day traders
- Momentum strategies
- News/event trading

**Interval suggestions:**
- 15m timeframe → 900s interval (check every 15 minutes)
- 30m timeframe → 1800s interval (check every 30 minutes)
- 1h timeframe → 3600s interval (check every hour)

---

### 4-Hour (Position Intraday)
**Pros:**
- Strong trend signals
- Lower noise
- 2-6 trades per day
- Better risk/reward ratios

**Cons:**
- Fewer opportunities
- Requires patience
- Positions held longer

**Recommended for:**
- Part-time traders
- Trend-following strategies
- Those with day jobs

**Interval suggestions:**
- 4h timeframe → 14400s interval (check every 4 hours)

---

### Daily (Swing/Position Trading - Default)
**Pros:**
- Best signal quality
- Lowest noise
- No intraday data limits
- Can analyze years of history
- Minimal time commitment

**Cons:**
- Fewer trading opportunities
- Overnight risk
- Slower feedback

**Recommended for:**
- Most traders (default choice)
- Swing trading strategies
- Those trading part-time
- Model training and backtesting

**Interval suggestions:**
- 1d timeframe → 3600-86400s interval (check hourly to daily)

---

### Weekly/Monthly (Long-Term)
**Pros:**
- Strongest trend signals
- Minimal noise
- Very low time commitment
- Ideal for position trading

**Cons:**
- Very few opportunities
- Long holding periods
- Significant overnight/weekend risk

**Recommended for:**
- Long-term investors
- Pension/retirement accounts
- Low-maintenance strategies

**Interval suggestions:**
- 1w timeframe → 86400s interval (check daily)
- 1mo timeframe → 86400s interval (check daily)

## Important Considerations

### Data Availability Limits

⚠️ **Intraday Limitation**: Yahoo Finance (yfinance) restricts intraday data (1m-1h) to the **last 60 days only**.

This means:
- Cannot fetch more than 60 days of 1m, 5m, 15m, 30m, or 1h data
- Model training on intraday timeframes limited to ~60 days
- Backtesting limited to 60-day windows for intraday

**Daily and longer timeframes** (1d, 1w, 1mo) have no such limitation and can fetch years of historical data.

### Timeframe vs Interval

These are **different concepts**:

- **Timeframe** (`--timeframe`): Resolution of each candle/bar (e.g., 5m = each bar is 5 minutes)
- **Interval** (`--interval`): How often the trading loop runs (in seconds)

**Best practice**: Set interval to match or be a multiple of timeframe.

Examples:
```bash
# ✅ Good: Check every bar
--timeframe 5m --interval 300  # 300s = 5 minutes

# ✅ Good: Check every 4 bars
--timeframe 5m --interval 1200  # 1200s = 20 minutes = 4 bars

# ⚠️ Suboptimal: Check more often than new bars arrive
--timeframe 5m --interval 60  # Checking every minute but only new data every 5min

# ❌ Bad: Missing many bars
--timeframe 1m --interval 3600  # New bar every minute, but only checking hourly
```

### 4-Hour Timeframe Special Case

The `4h` timeframe is **resampled from 1h data** because yfinance doesn't provide native 4h bars.

The system:
1. Fetches 1-hour bars from yfinance
2. Resamples to 4-hour using OHLC aggregation:
   - Open: First 1h bar in 4h period
   - High: Max of 4 × 1h highs
   - Low: Min of 4 × 1h lows
   - Close: Last 1h bar in 4h period
   - Volume: Sum of 4 × 1h volumes

This is accurate and widely used in trading platforms.

## Example Trading Strategies by Timeframe

### 5-Minute Scalping Strategy
```bash
# Fast scalping on EUR/USD
./scripts/start_paper.sh \
    --timeframe 5m \
    --interval 300 \
    --symbols eurusd \
    --capital 10000
```

**Target:** 5-10 pips per trade, 20-50 trades/day

---

### 1-Hour Swing Intraday
```bash
# Swing trade major Forex pairs
./scripts/start_paper.sh \
    --timeframe 1h \
    --interval 3600 \
    --symbols eurusd gbpusd usdjpy \
    --capital 50000
```

**Target:** 20-50 pips per trade, 2-8 trades/day

---

### 4-Hour Position Trading
```bash
# Position trade with lower frequency
./scripts/start_paper.sh \
    --timeframe 4h \
    --interval 14400 \
    --symbols eurusd gold \
    --capital 100000
```

**Target:** 50-150 pips per trade, 0-3 trades/day

---

### Daily Swing Trading (Default)
```bash
# Classic swing trading
./scripts/start_paper.sh \
    --timeframe 1d \
    --interval 3600 \
    --symbols eurusd gbpusd gold \
    --capital 100000
```

**Target:** 100-500 pips per trade, 1-5 trades/week

## Model Training for Different Timeframes

When training models, consider the timeframe you'll trade on:

```bash
# Train on 5-minute data (last 60 days only)
python scripts/train.py \
    --symbols eurusd \
    --timeframe 5m \
    --lookback 60 \
    --epochs 50

# Train on daily data (years of history)
python scripts/train.py \
    --symbols eurusd \
    --timeframe 1d \
    --lookback 365 \
    --epochs 50
```

**Recommendation**: Daily timeframe for initial model development, then optimize for other timeframes.

## Monitoring and Dashboards

Both Streamlit dashboards work with all timeframes:

- **Paper Monitor** (`http://localhost:8501`) - Real-time PnL and trades
- **Feature Explorer** (`http://localhost:8502`) - Data and feature analysis

The dashboards automatically adapt to your chosen timeframe.

## Performance Considerations

| Timeframe | CPU Usage | Memory | Network | Disk I/O |
|-----------|-----------|--------|---------|----------|
| 1m-5m | High | Medium | High | High |
| 15m-1h | Medium | Medium | Medium | Medium |
| 4h-1d | Low | Low | Low | Low |
| 1w-1mo | Very Low | Low | Very Low | Low |

**For production**: Higher-frequency timeframes (1m-15m) may require:
- Dedicated servers/VMs
- Faster CPU
- SSD storage
- Low-latency network
- More RAM for tick data

## Troubleshooting

### "No data returned" for Intraday Timeframes

**Problem**: Trying to fetch >60 days of intraday data

**Solution**: Reduce lookback or use daily timeframe
```bash
# This will work
--timeframe 5m --lookback 50

# This won't (60+ days)
--timeframe 5m --lookback 100
```

### High CPU Usage with Short Intervals

**Problem**: Checking too frequently (e.g., 1s interval)

**Solution**: Match interval to timeframe
```bash
# Don't do this
--timeframe 5m --interval 1

# Do this instead
--timeframe 5m --interval 300
```

### Missing Trades on Fast Timeframes

**Problem**: Interval too long for timeframe

**Solution**: Check at least every N bars
```bash
# For 1m timeframe, check at most every 5 minutes
--timeframe 1m --interval 300

# Better: check every minute
--timeframe 1m --interval 60
```

## Best Practices

1. **Start with daily** - Get the system working with `1d` timeframe first
2. **Match interval to timeframe** - Set interval = timeframe duration
3. **Consider data limits** - Remember 60-day limit for intraday
4. **Test before live** - Paper trade each timeframe for 1-2 weeks minimum
5. **Lower capital for faster timeframes** - More trades = more risk
6. **Monitor performance** - CPU/memory usage increases with frequency
7. **Backtest thoroughly** - More data points = more statistical significance

## Recommended Starting Configuration

```bash
# Beginner-friendly: Daily swing trading
./scripts/start_paper.sh \
    --timeframe 1d \
    --interval 3600 \
    --symbols eurusd \
    --capital 100000

# Intermediate: 1-hour intraday
./scripts/start_paper.sh \
    --timeframe 1h \
    --interval 3600 \
    --symbols eurusd gbpusd \
    --capital 50000

# Advanced: 5-minute scalping
./scripts/start_paper.sh \
    --timeframe 5m \
    --interval 300 \
    --symbols eurusd \
    --capital 10000
```

## Summary

✅ **Supported**: 1m, 2m, 5m, 15m, 30m, 1h, 90m, 4h, 1d, 1w, 1mo

⚠️ **Intraday Limit**: 60 days for m/h timeframes

🎯 **Recommended**: Start with `1d` (daily), then explore others

📊 **Most Popular**: 5m (scalping), 1h (intraday), 1d (swing), 4h (position)

🚀 **Easy to Use**: Just add `--timeframe <code>` to any command!

---

**Questions?** Check logs in `logs/paper_trading.log` or open an issue on GitHub.
