interface OrderTicketProps {
  orderSize: number;
  setOrderSize: (val: number) => void;
  handleBuy: () => void;
  handleSell: () => void;
  errorMsg: string | null;
  successMsg: string | null;
}

export function OrderTicket({
  orderSize,
  setOrderSize,
  handleBuy,
  handleSell,
  errorMsg,
  successMsg,
}: OrderTicketProps) {
  return (
    <div className="glass-panel" style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontWeight: 600, fontSize: 13, color: 'var(--text-primary)' }}>Order Ticket</span>
        <span style={{ fontSize: 10, background: 'rgba(255,255,255,0.04)', padding: '2px 6px', borderRadius: 3 }}>Market Execution</span>
      </div>

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
          style={{ flex: 1, background: '#111827', border: '1px solid var(--border-glow)', padding: '6px 10px', borderRadius: 4, color: '#fff', fontSize: 13 }}
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
            boxShadow: '0 0 10px var(--neon-green-glow)'
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
            boxShadow: '0 0 10px var(--neon-red-glow)'
          }}
        >
          SELL
        </button>
      </div>
    </div>
  );
}
