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

  presetEnabled: boolean;
  presetEntryPrice: number;
  setPresetEntryPrice: (val: number) => void;
  onTogglePreset: (val: boolean) => void;

  slEnabled: boolean;
  slPrice: number;
  setSlPrice: (val: number) => void;
  onToggleSL: (val: boolean) => void;

  tpEnabled: boolean;
  tpPrice: number;
  setTpPrice: (val: number) => void;
  onToggleTP: (val: boolean) => void;

  orderSide: 'buy' | 'sell';
  onToggleSide: (side: 'buy' | 'sell') => void;
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

  presetEnabled,
  presetEntryPrice,
  setPresetEntryPrice,
  onTogglePreset,

  slEnabled,
  slPrice,
  setSlPrice,
  onToggleSL,

  tpEnabled,
  tpPrice,
  setTpPrice,
  onToggleTP,

  orderSide,
  onToggleSide,
}: OrderTicketProps) {
  return (
    <div
      className="glass-panel"
      style={{
        padding: 14,
        display: 'flex',
        flexDirection: 'column',
        gap: isCollapsed ? 0 : 8,
        height: '100%',
        boxSizing: 'border-box',
        justifyContent: isCollapsed ? 'center' : 'flex-start',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontWeight: 600, fontSize: 13, color: 'var(--text-primary)' }}>Order Ticket</span>
          <span style={{ fontSize: 10, background: 'rgba(255,255,255,0.04)', padding: '2px 6px', borderRadius: 3, color: 'var(--text-secondary)' }}>
            Execution Levels
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

              {/* BUY / SELL Tab Selector */}
              <div style={{ display: 'flex', background: '#111827', borderRadius: '6px', padding: '2px', border: '1px solid var(--border-glow)' }}>
                <button
                  onClick={() => onToggleSide('buy')}
                  style={{
                    flex: 1,
                    background: orderSide === 'buy' ? 'var(--neon-green-glow)' : 'transparent',
                    border: 'none',
                    color: orderSide === 'buy' ? '#fff' : 'var(--text-secondary)',
                    padding: '6px 0',
                    borderRadius: '4px',
                    fontSize: '11px',
                    fontWeight: 700,
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                    textShadow: orderSide === 'buy' ? '0 0 5px var(--neon-green-glow)' : 'none',
                  }}
                >
                  BUY (LONG)
                </button>
                <button
                  onClick={() => onToggleSide('sell')}
                  style={{
                    flex: 1,
                    background: orderSide === 'sell' ? 'var(--neon-red-glow)' : 'transparent',
                    border: 'none',
                    color: orderSide === 'sell' ? '#fff' : 'var(--text-secondary)',
                    padding: '6px 0',
                    borderRadius: '4px',
                    fontSize: '11px',
                    fontWeight: 700,
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                    textShadow: orderSide === 'sell' ? '0 0 5px var(--neon-red-glow)' : 'none',
                  }}
                >
                  SELL (SHORT)
                </button>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{ fontSize: 12, color: 'var(--text-secondary)', fontWeight: 600 }}>LOT SIZE:</span>
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

              {/* Optional Preset Limit Price, SL, TP */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', margin: '4px 0' }}>
                {/* Limit Entry */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '10px' }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', color: 'var(--text-secondary)', cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={presetEnabled}
                      onChange={(e) => onTogglePreset(e.target.checked)}
                      style={{ accentColor: 'var(--neon-cyan)', cursor: 'pointer' }}
                    />
                    Limit Entry Price
                  </label>
                  {presetEnabled && (
                    <input
                      type="number"
                      step="0.00001"
                      value={presetEntryPrice}
                      onChange={(e) => setPresetEntryPrice(Number(e.target.value))}
                      style={{
                        width: '100px',
                        background: '#111827',
                        border: '1px solid var(--border-glow)',
                        padding: '4px 8px',
                        borderRadius: 4,
                        color: '#fff',
                        fontSize: '11px',
                        textAlign: 'right',
                      }}
                    />
                  )}
                </div>

                {/* Stop Loss */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '10px' }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', color: 'var(--text-secondary)', cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={slEnabled}
                      onChange={(e) => onToggleSL(e.target.checked)}
                      style={{ accentColor: 'var(--neon-red)', cursor: 'pointer' }}
                    />
                    Stop Loss (SL)
                  </label>
                  {slEnabled && (
                    <input
                      type="number"
                      step="0.00001"
                      value={slPrice}
                      onChange={(e) => setSlPrice(Number(e.target.value))}
                      style={{
                        width: '100px',
                        background: '#111827',
                        border: '1px solid var(--border-glow)',
                        padding: '4px 8px',
                        borderRadius: 4,
                        color: '#fff',
                        fontSize: '11px',
                        textAlign: 'right',
                      }}
                    />
                  )}
                </div>

                {/* Take Profit */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '10px' }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', color: 'var(--text-secondary)', cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={tpEnabled}
                      onChange={(e) => onToggleTP(e.target.checked)}
                      style={{ accentColor: 'var(--neon-green)', cursor: 'pointer' }}
                    />
                    Take Profit (TP)
                  </label>
                  {tpEnabled && (
                    <input
                      type="number"
                      step="0.00001"
                      value={tpPrice}
                      onChange={(e) => setTpPrice(Number(e.target.value))}
                      style={{
                        width: '100px',
                        background: '#111827',
                        border: '1px solid var(--border-glow)',
                        padding: '4px 8px',
                        borderRadius: 4,
                        color: '#fff',
                        fontSize: '11px',
                        textAlign: 'right',
                      }}
                    />
                  )}
                </div>
              </div>

              {/* Single execution button that adapts to BUY/SELL mode */}
              <div style={{ marginTop: 4 }}>
                <button
                  onClick={orderSide === 'buy' ? handleBuy : handleSell}
                  style={{
                    width: '100%',
                    padding: '10px',
                    borderRadius: 6,
                    background: orderSide === 'buy' ? 'var(--neon-green)' : 'var(--neon-red)',
                    color: orderSide === 'buy' ? '#000' : '#fff',
                    border: 'none',
                    fontWeight: 700,
                    cursor: 'pointer',
                    fontSize: 13,
                    boxShadow: orderSide === 'buy' ? '0 0 10px var(--neon-green-glow)' : '0 0 10px var(--neon-red-glow)',
                    transition: 'all 0.15s ease',
                  }}
                >
                  {orderSide === 'buy' ? 'PLACE BUY ORDER' : 'PLACE SELL ORDER'}
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
