interface PortfolioStateProps {
  sessionState: any;
  formatCurrency: (val: number | undefined) => string;
  mode: string;
  handleClosePosition: (inst: string) => void;
}

export function PortfolioState({
  sessionState,
  formatCurrency,
  mode,
  handleClosePosition,
}: PortfolioStateProps) {
  return (
    <div className="glass-panel" style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 10 }}>
      <span style={{ fontWeight: 600, fontSize: 13 }}>Portfolio State</span>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <span style={{ fontSize: 10, color: 'var(--text-secondary)' }}>BALANCE</span>
          <span style={{ fontSize: 15, fontWeight: 700 }}>
            {formatCurrency(sessionState?.current_portfolio?.balance)}
          </span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <span style={{ fontSize: 10, color: 'var(--text-secondary)' }}>EQUITY</span>
          <span style={{ fontSize: 15, fontWeight: 700 }}>
            {formatCurrency(sessionState?.current_portfolio?.equity)}
          </span>
        </div>
      </div>

      {/* Position details */}
      <div style={{ marginTop: 5, borderTop: '1px solid rgba(255,255,255,0.04)', paddingTop: 8 }}>
        <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)' }}>OPEN POSITIONS</span>
        {sessionState?.open_positions && sessionState.open_positions.length > 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 6 }}>
            {sessionState.open_positions.map((pos: any, idx: number) => {
              const isLong = pos.side.toLowerCase() === 'buy' || pos.side.toLowerCase() === 'long';
              const isPnlWin = pos.unrealized_pnl >= 0;
              return (
                <div key={idx} style={{ 
                  display: 'flex', 
                  justifyContent: 'space-between', 
                  alignItems: 'center', 
                  background: 'rgba(255,255,255,0.02)', 
                  padding: 8, 
                  borderRadius: 6,
                  borderLeft: `3px solid ${isLong ? 'var(--neon-green)' : 'var(--neon-red)'}`
                }}>
                  <div style={{ display: 'flex', flexDirection: 'column' }}>
                    <span style={{ fontSize: 12, fontWeight: 700 }}>
                      {pos.instrument} <span style={{ color: isLong ? 'var(--neon-green)' : 'var(--neon-red)', fontSize: 10 }}>{isLong ? 'LONG' : 'SHORT'}</span>
                    </span>
                    <span style={{ fontSize: 10, color: 'var(--text-secondary)' }}>
                      Size: {pos.size} · Entry: {pos.entry_price.toFixed(5)}
                    </span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontSize: 12, fontWeight: 700, color: isPnlWin ? 'var(--neon-green)' : 'var(--neon-red)' }}>
                      {isPnlWin ? '+' : ''}{pos.unrealized_pnl.toFixed(2)}
                    </span>
                    {mode === 'manual' && (
                      <button 
                        onClick={() => handleClosePosition(pos.instrument)}
                        style={{ padding: '3px 6px', background: 'var(--neon-orange-glow)', border: '1px solid var(--neon-orange)', color: 'var(--neon-orange)', borderRadius: 4, fontSize: 9, cursor: 'pointer' }}
                      >
                        CLOSE
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div style={{ fontSize: 11, color: 'var(--text-muted)', textAlign: 'center', padding: 12 }}>No open positions.</div>
        )}
      </div>
    </div>
  );
}
