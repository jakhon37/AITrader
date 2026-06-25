import { usePortfolioStore } from '../../store/portfolio';
import { Briefcase } from 'lucide-react';

function StatRow({ label, value, colored }: { label: string; value: string; colored?: boolean }) {
  const isPos = colored ? parseFloat(value.replace(/[^0-9.-]/g, '')) >= 0 : null;
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '5px 0', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
      <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{label}</span>
      <span style={{ fontSize: 12, fontWeight: 600, color: colored ? (isPos ? 'var(--neon-green)' : 'var(--neon-red)') : 'var(--text-primary)' }}>{value}</span>
    </div>
  );
}

export function Portfolio() {
  const p = usePortfolioStore((s) => s.portfolio);
  const fmt = (n: number) => n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const pct = (n: number) => (n * 100).toFixed(2) + '%';

  return (
    <div className="glass-panel panel-shell" style={{ padding: 16, gap: 8 }}>
      <h3
        className="panel-header"
        style={{
          fontSize: 11,
          fontWeight: 600,
          textTransform: 'uppercase',
          letterSpacing: '0.08em',
          color: 'var(--text-secondary)',
          marginBottom: 4,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
        }}
      >
        <Briefcase size={14} color="var(--neon-cyan)" /> Portfolio
      </h3>
      <div className="panel-header">
        <StatRow label="Balance" value={`$${fmt(p.balance)}`} />
        <StatRow label="Equity" value={`$${fmt(p.equity)}`} />
        <StatRow label="Free Margin" value={`$${fmt(p.free_margin)}`} />
        <StatRow label="P&L Today" value={`$${fmt(p.realized_pnl_today)}`} colored />
        <StatRow label="Drawdown" value={pct(p.drawdown_pct)} colored={p.drawdown_pct > 0} />
      </div>
      <div className="panel-body" style={{ marginTop: 4 }}>
        {p.open_positions.length === 0 ? (
          <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: 11, paddingTop: 12 }}>No open positions</div>
        ) : (
          <table className="terminal-table">
            <thead>
              <tr>
                <th>Sym</th>
                <th>Side</th>
                <th>Lots</th>
                <th>Entry</th>
                <th>PnL</th>
              </tr>
            </thead>
            <tbody>
              {p.open_positions.map((pos, i) => (
                <tr key={i}>
                  <td style={{ fontSize: 11 }}>{pos.instrument}</td>
                  <td style={{ fontSize: 11, fontWeight: 700, color: pos.side === 'buy' ? 'var(--neon-green)' : 'var(--neon-red)' }}>{pos.side.toUpperCase()}</td>
                  <td style={{ fontSize: 11 }}>{pos.size.toFixed(2)}</td>
                  <td style={{ fontSize: 11 }}>{pos.entry_price.toFixed(4)}</td>
                  <td style={{ fontSize: 11, fontWeight: 600, color: pos.unrealized_pnl >= 0 ? 'var(--neon-green)' : 'var(--neon-red)' }}>${fmt(pos.unrealized_pnl)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}