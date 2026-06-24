# Go-Live Checklist for AITrader

This checklist ensures all critical systems are ready before transitioning from paper trading to live trading with real money.

**Status:** Draft (Update as you complete paper trading)  
**Target Go-Live Date:** TBD (After 4-6 weeks paper trading)

---

## ✅ Phase 1: Paper Trading Validation (4-6 weeks)

### Week 1-2: System Stability
- [ ] Paper trading runs continuously for 2 weeks without crashes
- [ ] No unhandled exceptions in logs
- [ ] Circuit breaker triggers appropriately (test manually)
- [ ] Audit log captures all events correctly
- [ ] Position manager tracks PnL accurately
- [ ] Risk manager enforces all limits

### Week 3-4: Performance Validation
- [ ] Sharpe ratio > 0.5 in paper trading
- [ ] Win rate > 45%
- [ ] Max drawdown < 20%
- [ ] At least 20 trades executed
- [ ] No halts due to system errors
- [ ] Model predictions are reasonable (not random)

### Week 5-6: Edge Cases
- [ ] Test circuit breaker manual halt/resume
- [ ] Test risk limit violations (position size, daily loss)
- [ ] Handle missing data gracefully
- [ ] Handle network failures (if using live data)
- [ ] Test with multiple symbols
- [ ] Verify audit log retention and integrity

---

## ✅ Phase 2: Technical Readiness

### Infrastructure
- [ ] Production server/VM provisioned and secured
- [ ] SSH access configured with key-based auth
- [ ] Firewall rules configured (allow only necessary ports)
- [ ] SSL certificates installed (if web dashboard)
- [ ] Backup strategy defined (data, models, configs)
- [ ] Monitoring/alerting configured (CPU, memory, disk)

### Code & Configuration
- [ ] All tests passing (277+ tests)
- [ ] Production config created (`config/prod.yaml`)
- [ ] Secrets stored securely (`.env.prod`, not in git)
- [ ] Broker API credentials configured
- [ ] Database/storage for production data
- [ ] Log rotation configured (`logrotate`)

### Deployment
- [ ] Deployment script created (`scripts/deploy.sh`)
- [ ] Service/systemd unit configured for auto-restart
- [ ] Deployment tested on staging environment
- [ ] Rollback procedure documented
- [ ] Health check endpoint implemented

---

## ✅ Phase 3: Broker Integration

> **Planning:** See [broker-integration-roadmap.md](./broker-integration-roadmap.md) for
> current execution state, OANDA alternatives (IBKR, MT5, Dukascopy), and regional notes
> (e.g. South Korea, Uzbekistan).

### Broker Setup
- [ ] Real broker account opened (IBKR, MT5 broker, Dukascopy, or OANDA if available in your region)
- [ ] Account funded (start small: $5K-10K recommended)
- [ ] API access enabled
- [ ] API keys generated and stored securely
- [ ] API rate limits understood and documented
- [ ] Test orders placed on sandbox/demo account

### Broker Adapter
- [ ] Real broker adapter implemented (`src/execution/brokers/oanda.py`)
- [ ] Order submission tested on demo account
- [ ] Position tracking works correctly
- [ ] Error handling for API failures
- [ ] Rate limiting implemented
- [ ] Reconnection logic for network issues

### Compliance
- [ ] Understand broker's margin requirements
- [ ] Verify leverage limits
- [ ] Ensure compliance with broker's ToS
- [ ] Check if algorithmic trading is allowed
- [ ] Document broker fees and commissions

---

## ✅ Phase 4: Risk Management

### Position Sizing
- [ ] Max position size: $10K-20K (or 10-20% of capital)
- [ ] Max positions: 3-5 concurrent
- [ ] Max portfolio exposure: 60-80%
- [ ] Position sizing tested in paper trading

### Loss Limits
- [ ] Daily loss limit: 2% of capital
- [ ] Weekly loss limit: 5% of capital
- [ ] Max drawdown: 15%
- [ ] Circuit breaker thresholds validated

### Risk Controls
- [ ] Stop-loss orders implemented (optional)
- [ ] Take-profit orders implemented (optional)
- [ ] Maximum leverage: 1.0x (no leverage for Forex)
- [ ] Risk metrics monitored in dashboard

---

## ✅ Phase 5: Monitoring & Observability

### Logging
- [ ] All events logged to audit log
- [ ] Application logs centralized
- [ ] Log level set to INFO or WARNING in production
- [ ] Sensitive data (API keys) not logged

### Metrics
- [ ] Key metrics tracked:
  - [ ] Portfolio value
  - [ ] Daily PnL
  - [ ] Win rate
  - [ ] Sharpe ratio
  - [ ] Max drawdown
- [ ] Metrics exported to monitoring system (Prometheus, etc.)

### Alerts
- [ ] Alert on circuit breaker halt
- [ ] Alert on daily loss > 2%
- [ ] Alert on max drawdown > 15%
- [ ] Alert on system errors/crashes
- [ ] Alert on position close failures
- [ ] Alert on model prediction errors

### Dashboard
- [ ] Paper monitor dashboard accessible
- [ ] Feature explorer dashboard accessible
- [ ] Dashboard secured (password, VPN, etc.)
- [ ] Mobile-friendly for monitoring on the go

---

## ✅ Phase 6: Operations & Runbooks

### Daily Operations
- [ ] Daily checklist documented:
  - [ ] Check dashboard for alerts
  - [ ] Review overnight trades
  - [ ] Check audit log for errors
  - [ ] Monitor portfolio value
  - [ ] Check system health (CPU, memory, disk)

### Runbooks
- [ ] **Halt Trading**: `docs/runbooks/halt-trading.md`
- [ ] **Resume Trading**: `docs/runbooks/resume-trading.md`
- [ ] **Emergency Stop**: `docs/runbooks/emergency-stop.md`
- [ ] **Deploy Update**: `docs/runbooks/deploy-update.md`
- [ ] **Investigate Alert**: `docs/runbooks/investigate-alert.md`
- [ ] **Model Retraining**: `docs/runbooks/retrain-model.md`

### Disaster Recovery
- [ ] Backup strategy tested (data, models, configs)
- [ ] Recovery procedure documented
- [ ] Recovery tested (restore from backup)
- [ ] Backup retention policy defined (7 days, 30 days, etc.)

---

## ✅ Phase 7: Model & Data Quality

### Model Validation
- [ ] Model accuracy > 65% on validation set
- [ ] Model tested on out-of-sample data
- [ ] Model retrained in last 30 days
- [ ] Model metadata saved in registry
- [ ] Prediction latency < 1 second

### Data Quality
- [ ] Data pipeline validated (no missing data)
- [ ] Data freshness monitored (< 1 hour delay)
- [ ] Point-in-time guarantees enforced
- [ ] No future leakage detected

### Feature Monitoring
- [ ] Feature distributions stable (no drift)
- [ ] No features with > 10% missing values
- [ ] Feature importance updated monthly

---

## ✅ Phase 8: Legal & Compliance

### Legal
- [ ] Understand local regulations for algorithmic trading
- [ ] Consult with financial advisor (recommended)
- [ ] Understand tax implications
- [ ] Keep records for tax reporting (audit log)

### Compliance
- [ ] Broker's ToS accepted and understood
- [ ] No prohibited practices (market manipulation, etc.)
- [ ] Audit trail retention (5-7 years recommended)
- [ ] Privacy policy for any user data (if applicable)

---

## ✅ Phase 9: Final Pre-Launch Checks

### Configuration
- [ ] Production config reviewed and validated
- [ ] All secrets rotated and secured
- [ ] Database credentials secured
- [ ] API keys for production (not demo)

### Testing
- [ ] End-to-end test on production environment
- [ ] Small test trade (1 micro lot) executed successfully
- [ ] Position closed successfully
- [ ] PnL tracked correctly in audit log

### Team Readiness
- [ ] At least 2 people know how to operate the system
- [ ] Emergency contact list created
- [ ] Communication plan for incidents

---

## 🚀 Go-Live Procedure

### Day 0: Final Preparation
1. Review all checklist items
2. Backup all data and configs
3. Test production deployment
4. Enable monitoring and alerts
5. Set initial capital to small amount ($5K)

### Day 1: Launch
1. Deploy to production server
2. Start system in monitoring mode (dry-run)
3. Observe for 1 hour
4. Enable live trading with 1 symbol
5. Monitor closely for 4 hours
6. Check first trade execution

### Week 1: Ramp-Up
1. Monitor daily for issues
2. Gradually increase position sizes (if comfortable)
3. Add more symbols (if single symbol works)
4. Track performance vs paper trading
5. Review logs and metrics daily

### Week 2-4: Stabilization
1. Continue daily monitoring
2. Tune risk parameters if needed
3. Document any issues and fixes
4. Review model performance
5. Consider retraining if performance degrades

---

## 🛑 Abort Criteria

Stop trading immediately if:
- [ ] Daily loss exceeds 3%
- [ ] System crashes repeatedly
- [ ] Model predictions are erratic
- [ ] Broker API issues persist
- [ ] Data quality issues detected
- [ ] Circuit breaker triggers > 3 times/day

---

## 📞 Emergency Contacts

- **Broker Support**: [Phone/Email]
- **Hosting Provider**: [Phone/Email]
- **Team Member 2**: [Phone/Email]

---

## 📝 Sign-Off

Before going live, all stakeholders must sign off:

- [ ] **Technical Lead**: _________________ Date: _______
- [ ] **Risk Manager**: _________________ Date: _______
- [ ] **Compliance**: _________________ Date: _______

---

**Last Updated:** 2026-03-06  
**Next Review:** After 2 weeks of paper trading
