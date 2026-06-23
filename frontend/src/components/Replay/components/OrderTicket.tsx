import { ChevronDown, ChevronUp } from 'lucide-react';

interface OrderTicketProps {
  orderSize: number;
  setOrderSize: (val: number) => void;
  handleBuy: () => void;
  handleSell: () => void;
  errorMsg: string | null;
  successMsg: string | null;
  isCollapsed: boolean;
  onToggleCollapse: () => void;
  mode: 'watch' | 'manual';
}

export function OrderTicket({
  orderSize,
  setOrderSize,
  handleBuy,
  handleSell,
  errorMsg,
  successMsg,
  isCollapsed,
  onToggleCollapse,
  mode,
}: OrderTicketProps) {
  return (
    <div
      className="glass-panel"
      style={{
        padding: 14,
        display: 'flex',
        flexDirection: 'column',
        gap: isCollapsed ? 0 : 10,
        height: '100%',
        boxSizing: 'border-box',
        justifyContent: isCollapsed ? 'center' : 'flex-start',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontWeight: 600, fontSize: 13, color: 'var(--text-primary)' }}>Order Ticket</span>
          <span style={{ fontSize: 10, background: 'rgba(255,255,255,0.04)', padding: '2px 6px', borderRadius: 3, color: 'var(--text-secondary)' }}>
            Market Execution
          </span>
        </div>
        <button
          onClick={onToggleCollapse}
          title={isCollapsed ? "Expand Order Ticket" : "Collapse Order Ticket"}
          style={{
            background: 'transparent',
            border: 'none',
            color: 'var(--text-muted)',
            cursor: 'pointer',
            padding: '2px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            borderRadius: '4px',
            transition: 'color 0.2s',
          }}
          onMouseEnter={(e) => (e.currentTarget.style.color = '#fff')}
          onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-muted)')}
        >
          {isCollapsed ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
        </button>
      </div>

      {!isCollapsed && (
        <>
          {mode === 'manual' ? (
            <>
              {errorMsg && (
                <div style={{ fontSize: 11, color: 'var(--neon-red)', background: 'rgba(255,23,68,0.05)', padding: 6, borderRadius: 4 }}>
                  {errorMsg}
                </div>
              )}
              {successMsg && (
                <div style={{ fontSize: 11, color: 'var(--neon-green)', background: 'rgba(0,230,118,0.05)', padding: 6, borderRadius: 4 }}>
                  {successMsg}
                </div>
              )}

              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>LOT SIZE:</span>
                <input
                  type="number"
                  step="0.01"
                  value={orderSize}
                  onChange={(e) => setOrderSize(Math.max(0.01, Number(e.target.value)))}
                  style={{
                    flex: 1,
                    background: '#111827',
                    border: '1px solid var(--border-glow)',
                    padding: '6px 10px',
                    borderRadius: 4,
                    color: '#fff',
                    fontSize: 13,
                  }}
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                <button
                  onClick={handleBuy}
                  style={{
                    padding: '10px',
                    borderRadius: 6,
                    background: 'var(--neon-green)',
                    color: '#000',
                    border: 'none',
                    fontWeight: 700,
                    cursor: 'pointer',
                    fontSize: 13,
                    boxShadow: '0 0 10px var(--neon-green-glow)',
                  }}
                >
                  BUY
                </button>
                <button
                  onClick={handleSell}
                  style={{
                    padding: '10px',
                    borderRadius: 6,
                    background: 'var(--neon-red)',
                    color: '#fff',
                    border: 'none',
                    fontWeight: 700,
                    cursor: 'pointer',
                    fontSize: 13,
                    boxShadow: '0 0 10px var(--neon-red-glow)',
                  }}
                >
                  SELL
                </button>
              </div>
            </>
          ) : (
            <div className="glass-panel" style={{ padding: 14, textAlign: 'center', color: 'var(--text-secondary)', fontSize: 12, border: 'none', background: 'rgba(0,0,0,0.1)' }}>
              Manual trades are disabled in Strategy Watch Mode.
            </div>
          )}
        </>
      )}
    </div>
  );
}
