import type { RefObject } from 'react';
import { BarChart2 } from 'lucide-react';

interface SessionTradeLogProps {
  sessionState: any;
  tradeLogEndRef: RefObject<HTMLDivElement | null>;
}

export function SessionTradeLog({
  sessionState,
  tradeLogEndRef,
}: SessionTradeLogProps) {
  return (
    <div
      className="glass-panel"
      style={{
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        height: '100%',
        minHeight: 0,
        boxSizing: 'border-box',
      }}
    >
      <div
        style={{
          padding: '10px 14px',
          borderBottom: '1px solid rgba(255,255,255,0.06)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexShrink: 0,
        }}
      >
        <span style={{ fontWeight: 600, fontSize: 13, display: 'flex', alignItems: 'center', gap: 4 }}>
          <BarChart2 size={14} />
          Session Trade Log
        </span>
        <span style={{ fontSize: 10, color: 'var(--text-secondary)' }}>
          Count: {sessionState?.trade_history?.length || 0}
        </span>
      </div>

      <div
        style={{
          flex: 1,
          minHeight: 0,
          overflowY: 'auto',
          overflowX: 'hidden',
          padding: 8,
          WebkitOverflowScrolling: 'touch',
        }}
      >
        {sessionState?.trade_history && sessionState.trade_history.length > 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {sessionState.trade_history.map((t: any, idx: number) => {
              const isTradeWin = t.pnl >= 0;
              return (
                <div key={idx} style={{ 
                  display: 'flex', 
                  justifyContent: 'space-between', 
                  alignItems: 'center', 
                  background: 'rgba(255,255,255,0.01)', 
                  padding: '6px 8px', 
                  borderRadius: 4,
                  fontSize: 11
                }}>
                  <div style={{ display: 'flex', flexDirection: 'column' }}>
                    <span style={{ fontWeight: 600, color: t.side === 'long' ? 'var(--neon-green)' : 'var(--neon-red)' }}>
                      {t.side.toUpperCase()} · {t.size} Lots
                    </span>
                    <span style={{ fontSize: 9, color: 'var(--text-secondary)' }}>
                      In: {t.entry_price.toFixed(5)} · Out: {t.exit_price.toFixed(5)}
                    </span>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <span style={{ fontWeight: 700, color: isTradeWin ? 'var(--neon-green)' : 'var(--neon-red)' }}>
                      {isTradeWin ? '+' : ''}{t.pnl.toFixed(2)}
                    </span>
                    <div style={{ fontSize: 9, color: isTradeWin ? 'var(--neon-green)' : 'var(--neon-red)' }}>
                      {isTradeWin ? '+' : ''}{(t.pnl_pct * 100).toFixed(2)}%
                    </div>
                  </div>
                </div>
              );
            })}
            <div ref={tradeLogEndRef} />
          </div>
        ) : (
          <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)', fontSize: 12 }}>
            No completed trades.
          </div>
        )}
      </div>
    </div>
  );
}
