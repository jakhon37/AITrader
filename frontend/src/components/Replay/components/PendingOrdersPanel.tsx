import type { PendingOrder } from '../types';
import { formatPrice } from '../formatPrice';

interface PendingOrdersPanelProps {
  pendingOrders: PendingOrder[];
  instrument?: string;
  selectedPendingOrderId?: string | null;
  onSelectPendingOrder?: (order: PendingOrder) => void;
  compact?: boolean;
  listMaxHeight?: number;
}

export function PendingOrdersPanel({
  pendingOrders,
  instrument = 'EURUSD',
  selectedPendingOrderId = null,
  onSelectPendingOrder,
  compact = false,
  listMaxHeight,
}: PendingOrdersPanelProps) {
  if (pendingOrders.length === 0) {
    return (
      <div
        style={{
          fontSize: 11,
          color: 'var(--text-muted)',
          padding: compact ? '4px 0' : '8px 10px',
          background: compact ? 'transparent' : 'rgba(255,255,255,0.02)',
          borderRadius: 4,
        }}
      >
        No pending limit orders
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      {!compact && (
        <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.06em', color: 'var(--text-secondary)', textTransform: 'uppercase' }}>
          Pending Limits ({pendingOrders.length})
        </span>
      )}
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 4,
          maxHeight: listMaxHeight ?? (compact ? 90 : 140),
          overflowY: 'auto',
        }}
      >
        {pendingOrders.map((order) => {
          const selected = order.order_id === selectedPendingOrderId;
          const sideColor = order.side === 'buy' ? 'var(--neon-green)' : 'var(--neon-red)';
          return (
            <button
              key={order.order_id}
              type="button"
              onClick={() => onSelectPendingOrder?.(order)}
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                gap: 8,
                width: '100%',
                padding: compact ? '5px 8px' : '6px 8px',
                borderRadius: 4,
                border: `1px solid ${selected ? 'var(--neon-cyan)' : 'rgba(255,255,255,0.08)'}`,
                background: selected ? 'rgba(0, 229, 255, 0.08)' : 'rgba(255,255,255,0.02)',
                color: '#fff',
                cursor: 'pointer',
                textAlign: 'left',
              }}
            >
              <span style={{ fontSize: 11, fontWeight: 700, color: sideColor, textTransform: 'uppercase', minWidth: 36 }}>
                {order.side}
              </span>
              <span style={{ fontSize: 11, flex: 1 }}>
                {order.size_lots} lot @ {formatPrice(order.entry_price, instrument)}
              </span>
              <span style={{ fontSize: 9, color: 'var(--text-muted)' }}>{selected ? 'On chart' : 'Show'}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}