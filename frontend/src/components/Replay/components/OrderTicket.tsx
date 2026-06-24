import { ChevronDown, ChevronUp } from 'lucide-react';
import type { PendingOrder } from '../types';
import { roundPrice, priceInputStep } from '../formatPrice';
import { PendingOrdersPanel } from './PendingOrdersPanel';

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
  currentClosePrice: number;

  pendingOrders?: PendingOrder[];
  selectedPendingOrderId?: string | null;
  onSelectPendingOrder?: (order: PendingOrder) => void;
  onClearPendingSelection?: () => void;
  onCancelPendingOrder?: () => void;
  onUpdatePendingOrder?: () => void;

  editingOpenPosition?: boolean;
  onClearOpenPositionSelection?: () => void;
  instrument?: string;
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
  currentClosePrice,
  pendingOrders = [],
  selectedPendingOrderId = null,
  onSelectPendingOrder,
  onClearPendingSelection,
  onCancelPendingOrder,
  onUpdatePendingOrder,
  editingOpenPosition = false,
  onClearOpenPositionSelection,
  instrument = 'EURUSD',
}: OrderTicketProps) {
  const editingPending = !!selectedPendingOrderId;
  const showOrderForm = !editingOpenPosition;
  const entryPrice = presetEnabled ? presetEntryPrice : currentClosePrice;
  const priceStep = priceInputStep(instrument);
  const round = (price: number) => roundPrice(price, instrument);

  let estLoss = 0;
  let lossPct = 0;
  if (slEnabled && entryPrice > 0) {
    const diff = orderSide === 'buy' ? (entryPrice - slPrice) : (slPrice - entryPrice);
    estLoss = diff * orderSize * 100000;
    lossPct = (diff / entryPrice) * 100;
  }

  let estProfit = 0;
  let profitPct = 0;
  if (tpEnabled && entryPrice > 0) {
    const diff = orderSide === 'buy' ? (tpPrice - entryPrice) : (entryPrice - tpPrice);
    estProfit = diff * orderSize * 100000;
    profitPct = (diff / entryPrice) * 100;
  }

  const actionButtons = (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <button
        onClick={editingPending ? onUpdatePendingOrder : (orderSide === 'buy' ? handleBuy : handleSell)}
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
        {editingPending
          ? 'UPDATE LIMIT ORDER'
          : orderSide === 'buy'
            ? 'PLACE BUY ORDER'
            : 'PLACE SELL ORDER'}
      </button>
      {editingPending && onCancelPendingOrder && (
        <button
          type="button"
          onClick={onCancelPendingOrder}
          style={{
            width: '100%',
            padding: '8px',
            borderRadius: 6,
            background: 'rgba(255, 23, 68, 0.12)',
            color: '#ff5252',
            border: '1px solid var(--neon-red)',
            fontWeight: 600,
            cursor: 'pointer',
            fontSize: 12,
          }}
        >
          CANCEL PENDING ORDER
        </button>
      )}
      {editingPending && onClearPendingSelection && (
        <button
          type="button"
          onClick={onClearPendingSelection}
          style={{
            width: '100%',
            padding: '6px 8px',
            borderRadius: 4,
            border: '1px solid var(--neon-cyan)',
            background: 'rgba(0, 229, 255, 0.08)',
            color: 'var(--neon-cyan)',
            fontSize: 11,
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          + Place another limit order
        </button>
      )}
    </div>
  );

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
        overflow: 'hidden',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontWeight: 600, fontSize: 13, color: 'var(--text-primary)' }}>Order Ticket</span>
          <span style={{ fontSize: 10, background: 'rgba(255,255,255,0.04)', padding: '2px 6px', borderRadius: 3, color: 'var(--text-secondary)' }}>
            Execution Levels
          </span>
          {pendingOrders.length > 0 && (
            <span style={{ fontSize: 10, background: 'rgba(0, 229, 255, 0.15)', padding: '2px 6px', borderRadius: 3, color: 'var(--neon-cyan)', fontWeight: 700 }}>
              {pendingOrders.length} pending
            </span>
          )}
        </div>
        <button
          onClick={onToggleCollapse}
          title={isCollapsed ? 'Expand Order Ticket' : 'Collapse Order Ticket'}
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

      {mode === 'manual' && pendingOrders.length > 0 && (
        <div style={{ flexShrink: 0, marginTop: isCollapsed ? 6 : 0 }}>
          <PendingOrdersPanel
            pendingOrders={pendingOrders}
            instrument={instrument}
            selectedPendingOrderId={selectedPendingOrderId}
            onSelectPendingOrder={onSelectPendingOrder}
            compact={isCollapsed}
            listMaxHeight={isCollapsed ? 72 : 140}
          />
        </div>
      )}

      {!isCollapsed && (
        <>
          {mode === 'manual' ? (
            <>
              <div
                style={{
                  flex: 1,
                  minHeight: 0,
                  overflowY: 'auto',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 8,
                  paddingRight: 2,
                }}
              >
                {errorMsg && (
                  <div style={{ fontSize: 11, color: 'var(--neon-red)', background: 'rgba(255,23,68,0.05)', padding: 6, borderRadius: 4 }}>
                    {errorMsg}
                  </div>
                )}
                {successMsg && !editingOpenPosition && (
                  <div style={{ fontSize: 11, color: 'var(--neon-green)', background: 'rgba(0,230,118,0.05)', padding: 6, borderRadius: 4 }}>
                    {successMsg}
                  </div>
                )}

                {editingOpenPosition && (
                  <div
                    style={{
                      padding: 10,
                      borderRadius: 6,
                      border: '1px solid rgba(0, 229, 255, 0.25)',
                      background: 'rgba(0, 229, 255, 0.06)',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 8,
                    }}
                  >
                    <span style={{ fontSize: 11, color: 'var(--neon-cyan)', fontWeight: 600 }}>
                      Editing open position
                    </span>
                    <span style={{ fontSize: 10, color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                      Adjust SL/TP or close the position in Portfolio State below. Use Order Ticket for new orders and pending limits.
                    </span>
                    {onClearOpenPositionSelection && (
                      <button
                        type="button"
                        onClick={onClearOpenPositionSelection}
                        style={{
                          alignSelf: 'flex-start',
                          padding: '5px 10px',
                          borderRadius: 4,
                          border: '1px solid var(--border-glow)',
                          background: 'rgba(255,255,255,0.04)',
                          color: 'var(--text-secondary)',
                          fontSize: 10,
                          fontWeight: 600,
                          cursor: 'pointer',
                        }}
                      >
                        Back to new orders
                      </button>
                    )}
                  </div>
                )}

                {showOrderForm && (
                <>
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

                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', margin: '4px 0' }}>
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
                        step={priceStep}
                        value={round(presetEntryPrice)}
                        onChange={(e) => setPresetEntryPrice(round(Number(e.target.value)))}
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

                  <div>
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
                          step={priceStep}
                          value={round(slPrice)}
                          onChange={(e) => setSlPrice(round(Number(e.target.value)))}
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
                    {slEnabled && (
                      <div style={{ fontSize: '10px', color: '#ff1744', marginTop: '2px', paddingLeft: '20px', fontWeight: 600 }}>
                        Est. Loss: -${estLoss.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} (-{lossPct.toFixed(2)}%)
                      </div>
                    )}
                  </div>

                  <div>
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
                          step={priceStep}
                          value={round(tpPrice)}
                          onChange={(e) => setTpPrice(round(Number(e.target.value)))}
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
                    {tpEnabled && (
                      <div style={{ fontSize: '10px', color: '#00e676', marginTop: '2px', paddingLeft: '20px', fontWeight: 600 }}>
                        Est. Profit: +${estProfit.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} (+{profitPct.toFixed(2)}%)
                      </div>
                    )}
                  </div>
                </div>
                </>
                )}
              </div>

              {showOrderForm && (
              <div
                style={{
                  flexShrink: 0,
                  marginTop: 4,
                  paddingTop: 8,
                  borderTop: '1px solid rgba(255,255,255,0.06)',
                }}
              >
                {actionButtons}
              </div>
              )}
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