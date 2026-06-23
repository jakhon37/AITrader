import { Award, TrendingUp, TrendingDown, ShieldAlert } from 'lucide-react';

interface PerformanceScorecardProps {
  scorecard: any;
  instrument: string;
  setScorecard: (val: any) => void;
  formatCurrency: (val: number | undefined) => string;
}

export function PerformanceScorecard({
  scorecard,
  instrument,
  setScorecard,
  formatCurrency,
}: PerformanceScorecardProps) {
  const isWin = scorecard.net_profit >= 0;

  return (
    <div style={{ padding: 24, maxWidth: 750, margin: '30px auto', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid rgba(255,255,255,0.08)', paddingBottom: 15 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Award size={36} color="var(--neon-cyan)" />
          <div>
            <h2 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', margin: 0 }}>Performance Report Card</h2>
            <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: 0 }}>Manual Replay session completed for {instrument}.</p>
          </div>
        </div>
        <button 
          type="button"
          onClick={() => setScorecard(null)}
          style={{ 
            padding: '8px 16px', 
            background: '#111827', 
            border: '1px solid var(--border-glow)', 
            color: '#fff', 
            borderRadius: 6,
            cursor: 'pointer',
            fontSize: 13
          }}
        >
          Return to Studio
        </button>
      </div>

      {/* Scorecard grids */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
        <div className="glass-panel" style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 4 }}>
          <span style={{ fontSize: 11, color: 'var(--text-secondary)', fontWeight: 600 }}>FINAL EQUITY</span>
          <span style={{ fontSize: 22, fontWeight: 700 }}>{formatCurrency(scorecard.final_equity)}</span>
        </div>

        <div className="glass-panel" style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 4 }}>
          <span style={{ fontSize: 11, color: 'var(--text-secondary)', fontWeight: 600 }}>NET PROFIT</span>
          <span style={{ fontSize: 22, fontWeight: 700, color: isWin ? 'var(--neon-green)' : 'var(--neon-red)', display: 'flex', alignItems: 'center', gap: 4 }}>
            {isWin ? <TrendingUp size={20} /> : <TrendingDown size={20} />}
            {scorecard.net_profit >= 0 ? '+' : ''}{formatCurrency(scorecard.net_profit)} ({scorecard.net_profit_pct.toFixed(2)}%)
          </span>
        </div>

        <div className="glass-panel" style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 4 }}>
          <span style={{ fontSize: 11, color: 'var(--text-secondary)', fontWeight: 600 }}>DISCIPLINE SCORE</span>
          <span style={{ fontSize: 22, fontWeight: 700, color: scorecard.discipline_score >= 80 ? 'var(--neon-green)' : scorecard.discipline_score >= 50 ? 'var(--neon-orange)' : 'var(--neon-red)', display: 'flex', alignItems: 'center', gap: 6 }}>
            <ShieldAlert size={20} />
            {scorecard.discipline_score.toFixed(1)}%
          </span>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
        <div className="glass-panel" style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 4 }}>
          <span style={{ fontSize: 11, color: 'var(--text-secondary)', fontWeight: 600 }}>TOTAL TRADES</span>
          <span style={{ fontSize: 20, fontWeight: 700 }}>{scorecard.total_trades}</span>
        </div>

        <div className="glass-panel" style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 4 }}>
          <span style={{ fontSize: 11, color: 'var(--text-secondary)', fontWeight: 600 }}>WIN RATE</span>
          <span style={{ fontSize: 20, fontWeight: 700 }}>{scorecard.win_rate.toFixed(1)}%</span>
        </div>

        <div className="glass-panel" style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 4 }}>
          <span style={{ fontSize: 11, color: 'var(--text-secondary)', fontWeight: 600 }}>PROFIT FACTOR</span>
          <span style={{ fontSize: 20, fontWeight: 700 }}>{scorecard.profit_factor === Infinity ? '∞' : scorecard.profit_factor.toFixed(2)}</span>
        </div>
      </div>

      {/* Trade History details */}
      <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', height: 280 }}>
        <div style={{ padding: '12px 16px', borderBottom: '1px solid rgba(255,255,255,0.06)', fontWeight: 600, fontSize: 14 }}>
          Executed Trade Log
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: 8 }}>
          {scorecard.trades && scorecard.trades.length > 0 ? (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12, textAlign: 'left' }}>
              <thead>
                <tr style={{ color: 'var(--text-secondary)', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                  <th style={{ padding: '8px 12px' }}>Direction</th>
                  <th style={{ padding: '8px 12px' }}>Size</th>
                  <th style={{ padding: '8px 12px' }}>Entry Price</th>
                  <th style={{ padding: '8px 12px' }}>Exit Price</th>
                  <th style={{ padding: '8px 12px' }}>P&L ($)</th>
                  <th style={{ padding: '8px 12px' }}>P&L (%)</th>
                </tr>
              </thead>
              <tbody>
                {scorecard.trades.map((t: any, idx: number) => {
                  const isTradeWin = t.pnl >= 0;
                  return (
                    <tr key={idx} style={{ borderBottom: '1px solid rgba(255,255,255,0.02)', verticalAlign: 'middle' }}>
                      <td style={{ padding: '8px 12px', fontWeight: 600, color: t.side === 'long' ? 'var(--neon-green)' : 'var(--neon-red)' }}>
                        {t.side.toUpperCase()}
                      </td>
                      <td style={{ padding: '8px 12px' }}>{t.size.toFixed(2)}</td>
                      <td style={{ padding: '8px 12px' }}>{t.entry_price.toFixed(5)}</td>
                      <td style={{ padding: '8px 12px' }}>{t.exit_price.toFixed(5)}</td>
                      <td style={{ padding: '8px 12px', color: isTradeWin ? 'var(--neon-green)' : 'var(--neon-red)', fontWeight: 600 }}>
                        {isTradeWin ? '+' : ''}{t.pnl.toFixed(2)}
                      </td>
                      <td style={{ padding: '8px 12px', color: isTradeWin ? 'var(--neon-green)' : 'var(--neon-red)' }}>
                        {isTradeWin ? '+' : ''}{(t.pnl_pct * 100).toFixed(2)}%
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : (
            <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
              No trades were placed during this session.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
