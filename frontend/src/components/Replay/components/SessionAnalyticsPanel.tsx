import { Award, TrendingDown, TrendingUp, X } from 'lucide-react';
import type { SessionAnalytics } from '../types/analytics';
import { formatPrice } from '../formatPrice';
import { EquityCurveChart } from './EquityCurveChart';
import { ChartErrorBoundary } from './ChartErrorBoundary';

interface SessionAnalyticsPanelProps {
  analytics: SessionAnalytics;
  instrument: string;
  formatCurrency: (val: number | undefined) => string;
  loading?: boolean;
  finalMode?: boolean;
  onContinue?: () => void;
  onEndSession?: () => void;
  onClose?: () => void;
}

function MetricCard({
  label,
  value,
  sub,
  color,
}: {
  label: string;
  value: string;
  sub?: string;
  color?: string;
}) {
  return (
    <div className="glass-panel" style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 }}>
      <span style={{ fontSize: 10, color: 'var(--text-secondary)', fontWeight: 600, letterSpacing: '0.04em' }}>
        {label}
      </span>
      <span style={{ fontSize: 18, fontWeight: 700, color: color ?? '#fff', lineHeight: 1.2 }}>{value}</span>
      {sub && <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>{sub}</span>}
    </div>
  );
}

export function SessionAnalyticsPanel({
  analytics,
  instrument,
  formatCurrency,
  loading = false,
  finalMode = false,
  onContinue,
  onEndSession,
  onClose,
}: SessionAnalyticsPanelProps) {
  const inst = analytics.instrument ?? instrument;
  const isWin = (analytics.net_profit ?? 0) >= 0;
  const summary = analytics.summary;
  const tradePnls = analytics.trade_pnls ?? [];
  const trades = analytics.trades ?? [];
  const equityCurve = analytics.equity_curve ?? [];
  const maxPnl = Math.max(...tradePnls.map((t) => Math.abs(t.pnl)), 1);

  const formatMetric = (value: number | null | undefined, digits = 2) => {
    if (value == null || !Number.isFinite(value)) return '—';
    if (value === Infinity) return '∞';
    return value.toFixed(digits);
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 2000,
        background: 'rgba(4, 7, 14, 0.92)',
        backdropFilter: 'blur(8px)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '16px 24px',
          borderBottom: '1px solid rgba(255,255,255,0.08)',
          background: 'rgba(7, 9, 14, 0.95)',
          flexShrink: 0,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Award size={28} color="var(--neon-cyan)" />
          <div>
            <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: '#fff' }}>Session Analytics</h2>
            <p style={{ margin: 0, fontSize: 12, color: 'var(--text-secondary)' }}>
              {inst} · {analytics.total_trades} closed trades
              {analytics.open_positions ? ` · ${analytics.open_positions} still open` : ''}
              {analytics.current_time ? ` · ${new Date(analytics.current_time).toUTCString().replace('GMT', 'UTC')}` : ''}
            </p>
          </div>
        </div>
        {!finalMode && onClose && (
          <button
            type="button"
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--text-muted)',
              cursor: 'pointer',
              padding: 6,
            }}
          >
            <X size={20} />
          </button>
        )}
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px 24px' }}>
        {loading ? (
          <div style={{ padding: 60, textAlign: 'center', color: 'var(--text-secondary)' }}>Loading analytics…</div>
        ) : (
          <div style={{ maxWidth: 1200, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 18 }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12 }}>
              <MetricCard label="FINAL EQUITY" value={formatCurrency(analytics.final_equity)} />
              <MetricCard
                label="NET P&L"
                value={`${isWin ? '+' : ''}${formatCurrency(analytics.net_profit)}`}
                sub={`${analytics.net_profit_pct >= 0 ? '+' : ''}${analytics.net_profit_pct.toFixed(2)}%`}
                color={isWin ? 'var(--neon-green)' : 'var(--neon-red)'}
              />
              <MetricCard label="WIN RATE" value={`${formatMetric(analytics.win_rate, 1)}%`} sub={`${summary?.wins ?? 0}W / ${summary?.losses ?? 0}L`} />
              <MetricCard label="PROFIT FACTOR" value={formatMetric(analytics.profit_factor)} />
              <MetricCard label="MAX DRAWDOWN" value={`${formatMetric(analytics.max_drawdown_pct)}%`} color="var(--neon-orange)" />
              <MetricCard label="SHARPE" value={formatMetric(analytics.sharpe_ratio)} />
              <MetricCard label="AVG R:R" value={formatMetric(analytics.average_rr)} />
              <MetricCard
                label="DISCIPLINE"
                value={`${formatMetric(analytics.discipline_score, 1)}%`}
                color={(analytics.discipline_score ?? 0) >= 80 ? 'var(--neon-green)' : (analytics.discipline_score ?? 0) >= 50 ? 'var(--neon-orange)' : 'var(--neon-red)'}
              />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: 14, minHeight: 220 }}>
              <div className="glass-panel" style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 8, minHeight: 220 }}>
                <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)' }}>Equity Curve</span>
                <div style={{ flex: 1, minHeight: 180 }}>
                  <ChartErrorBoundary>
                    <EquityCurveChart data={equityCurve} initialCapital={analytics.initial_capital} />
                  </ChartErrorBoundary>
                </div>
              </div>

              <div className="glass-panel" style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 10 }}>
                <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)' }}>Trade Breakdown</span>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: 11 }}>
                  <div>
                    <span style={{ color: 'var(--text-muted)' }}>Avg Win</span>
                    <div style={{ color: 'var(--neon-green)', fontWeight: 700 }}>+{formatCurrency(summary?.avg_win)}</div>
                  </div>
                  <div>
                    <span style={{ color: 'var(--text-muted)' }}>Avg Loss</span>
                    <div style={{ color: 'var(--neon-red)', fontWeight: 700 }}>-{formatCurrency(summary?.avg_loss)}</div>
                  </div>
                  <div>
                    <span style={{ color: 'var(--text-muted)' }}>Best Trade</span>
                    <div style={{ color: 'var(--neon-green)', fontWeight: 700 }}>+{formatCurrency(summary?.best_trade)}</div>
                  </div>
                  <div>
                    <span style={{ color: 'var(--text-muted)' }}>Worst Trade</span>
                    <div style={{ color: 'var(--neon-red)', fontWeight: 700 }}>{formatCurrency(summary?.worst_trade)}</div>
                  </div>
                </div>
                <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginTop: 4 }}>P&L per Trade</span>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4, maxHeight: 120, overflowY: 'auto' }}>
                  {tradePnls.length === 0 ? (
                    <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>No closed trades yet.</span>
                  ) : (
                    tradePnls.map((t) => {
                      const win = t.pnl >= 0;
                      const width = Math.max(8, (Math.abs(t.pnl) / maxPnl) * 100);
                      return (
                        <div key={t.index} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 10 }}>
                          <span style={{ width: 24, color: 'var(--text-muted)' }}>#{t.index}</span>
                          <div style={{ flex: 1, height: 8, background: 'rgba(255,255,255,0.04)', borderRadius: 4, overflow: 'hidden' }}>
                            <div
                              style={{
                                width: `${width}%`,
                                height: '100%',
                                background: win ? 'var(--neon-green)' : 'var(--neon-red)',
                                borderRadius: 4,
                              }}
                            />
                          </div>
                          <span style={{ width: 72, textAlign: 'right', color: win ? 'var(--neon-green)' : 'var(--neon-red)', fontWeight: 600 }}>
                            {win ? '+' : ''}{t.pnl.toFixed(2)}
                          </span>
                        </div>
                      );
                    })
                  )}
                </div>
              </div>
            </div>

            <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', maxHeight: 280 }}>
              <div style={{ padding: '12px 16px', borderBottom: '1px solid rgba(255,255,255,0.06)', fontWeight: 600, fontSize: 13, display: 'flex', alignItems: 'center', gap: 8 }}>
                {isWin ? <TrendingUp size={16} color="var(--neon-green)" /> : <TrendingDown size={16} color="var(--neon-red)" />}
                Trade History
              </div>
              <div style={{ flex: 1, overflowY: 'auto', padding: 8 }}>
                {trades.length > 0 ? (
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11, textAlign: 'left' }}>
                    <thead>
                      <tr style={{ color: 'var(--text-secondary)', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                        <th style={{ padding: '8px 10px' }}>Side</th>
                        <th style={{ padding: '8px 10px' }}>Size</th>
                        <th style={{ padding: '8px 10px' }}>Entry</th>
                        <th style={{ padding: '8px 10px' }}>Exit</th>
                        <th style={{ padding: '8px 10px' }}>P&L</th>
                        <th style={{ padding: '8px 10px' }}>P&L %</th>
                        <th style={{ padding: '8px 10px' }}>Closed</th>
                      </tr>
                    </thead>
                    <tbody>
                      {trades.map((t, idx) => {
                        const win = t.pnl >= 0;
                        const isLong = t.side === 'long' || t.side === 'buy';
                        return (
                          <tr key={idx} style={{ borderBottom: '1px solid rgba(255,255,255,0.02)' }}>
                            <td style={{ padding: '8px 10px', fontWeight: 700, color: isLong ? 'var(--neon-green)' : 'var(--neon-red)' }}>
                              {isLong ? 'LONG' : 'SHORT'}
                            </td>
                            <td style={{ padding: '8px 10px' }}>{(t.size >= 1000 ? t.size / 100000 : t.size).toFixed(2)}</td>
                            <td style={{ padding: '8px 10px' }}>{formatPrice(t.entry_price, inst)}</td>
                            <td style={{ padding: '8px 10px' }}>{formatPrice(t.exit_price, inst)}</td>
                            <td style={{ padding: '8px 10px', color: win ? 'var(--neon-green)' : 'var(--neon-red)', fontWeight: 600 }}>
                              {win ? '+' : ''}{t.pnl.toFixed(2)}
                            </td>
                            <td style={{ padding: '8px 10px', color: win ? 'var(--neon-green)' : 'var(--neon-red)' }}>
                              {win ? '+' : ''}{(t.pnl_pct * 100).toFixed(2)}%
                            </td>
                            <td style={{ padding: '8px 10px', color: 'var(--text-muted)', fontSize: 10 }}>
                              {t.exit_time ? new Date(t.exit_time).toISOString().slice(0, 16).replace('T', ' ') : '—'}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                ) : (
                  <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-muted)' }}>
                    No closed trades yet. Open positions and pending orders are not included until closed.
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      <div
        style={{
          display: 'flex',
          justifyContent: 'flex-end',
          gap: 10,
          padding: '14px 24px',
          borderTop: '1px solid rgba(255,255,255,0.08)',
          background: 'rgba(7, 9, 14, 0.95)',
          flexShrink: 0,
        }}
      >
        {finalMode ? (
          <button
            type="button"
            onClick={onClose}
            style={{
              padding: '10px 20px',
              borderRadius: 6,
              border: '1px solid var(--neon-cyan)',
              background: 'var(--neon-cyan-glow)',
              color: '#fff',
              fontWeight: 700,
              fontSize: 13,
              cursor: 'pointer',
            }}
          >
            Return to Studio
          </button>
        ) : (
          <>
            <button
              type="button"
              onClick={onContinue}
              style={{
                padding: '10px 20px',
                borderRadius: 6,
                border: '1px solid var(--border-glow)',
                background: '#111827',
                color: '#fff',
                fontWeight: 600,
                fontSize: 13,
                cursor: 'pointer',
              }}
            >
              Continue Session
            </button>
            <button
              type="button"
              onClick={onEndSession}
              style={{
                padding: '10px 20px',
                borderRadius: 6,
                border: '1px solid var(--neon-red)',
                background: 'rgba(255, 23, 68, 0.12)',
                color: '#ff5252',
                fontWeight: 700,
                fontSize: 13,
                cursor: 'pointer',
              }}
            >
              End Session
            </button>
          </>
        )}
      </div>
    </div>
  );
}