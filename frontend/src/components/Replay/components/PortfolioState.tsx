import type { PositionSummary } from '../../../types';
import { formatPrice, roundPrice, priceInputStep } from '../formatPrice';

export interface OpenPositionDraft {
  slPrice: number;
  tpPrice: number;
  slEnabled: boolean;
  tpEnabled: boolean;
}

interface PortfolioStateProps {
  sessionState: any;
  formatCurrency: (val: number | undefined) => string;
  instrument: string;
  mode: string;
  successMsg?: string | null;
  selectedOpenLegId?: string | null;
  openPositionDraft?: OpenPositionDraft;
  onSelectOpenPosition?: (pos: PositionSummary) => void;
  onDraftSlToggle?: (enabled: boolean) => void;
  onDraftTpToggle?: (enabled: boolean) => void;
  onDraftSlChange?: (price: number) => void;
  onDraftTpChange?: (price: number) => void;
  onCloseLeg?: (legId: string) => void;
  onModifyLeg?: (
    legId: string,
    stopLoss: number | null,
    takeProfit: number | null,
    options?: { clearSl?: boolean; clearTp?: boolean },
  ) => void;
}

function OpenPositionRow({
  pos,
  instrument,
  mode,
  selected,
  draft,
  onSelect,
  onDraftSlToggle,
  onDraftTpToggle,
  onDraftSlChange,
  onDraftTpChange,
  onCloseLeg,
  onModifyLeg,
}: {
  pos: PositionSummary;
  instrument: string;
  mode: string;
  selected: boolean;
  draft?: OpenPositionDraft;
  onSelect?: () => void;
  onDraftSlToggle?: (enabled: boolean) => void;
  onDraftTpToggle?: (enabled: boolean) => void;
  onDraftSlChange?: (price: number) => void;
  onDraftTpChange?: (price: number) => void;
  onCloseLeg?: (legId: string) => void;
  onModifyLeg?: PortfolioStateProps['onModifyLeg'];
}) {
  const isLong = pos.side.toLowerCase() === 'buy' || pos.side.toLowerCase() === 'long';
  const isPnlWin = pos.unrealized_pnl >= 0;
  const sizeLots = pos.size >= 1000 ? pos.size / 100000 : pos.size;
  const legId = pos.leg_id ?? '';
  const priceStep = priceInputStep(instrument);
  const round = (price: number) => roundPrice(price, instrument);

  const handleUpdateLevels = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!legId || !onModifyLeg || !draft) return;
    onModifyLeg(
      legId,
      draft.slEnabled ? draft.slPrice : null,
      draft.tpEnabled ? draft.tpPrice : null,
      { clearSl: !draft.slEnabled, clearTp: !draft.tpEnabled },
    );
  };

  const handleClose = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (legId && onCloseLeg) onCloseLeg(legId);
  };

  const rowBorderColor = selected ? 'var(--neon-cyan)' : 'rgba(255,255,255,0.06)';

  return (
    <div
      style={{
        width: '100%',
        textAlign: 'left',
        background: selected ? 'rgba(0, 229, 255, 0.08)' : 'rgba(255,255,255,0.02)',
        padding: 8,
        borderRadius: 6,
        borderTop: `1px solid ${rowBorderColor}`,
        borderRight: `1px solid ${rowBorderColor}`,
        borderBottom: `1px solid ${rowBorderColor}`,
        borderLeft: `3px solid ${isLong ? 'var(--neon-green)' : 'var(--neon-red)'}`,
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        color: 'inherit',
      }}
    >
      <div
        role="button"
        tabIndex={0}
        onClick={onSelect}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onSelect?.();
          }
        }}
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          gap: 8,
          cursor: 'pointer',
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
          <span style={{ fontSize: 12, fontWeight: 700 }}>
            {pos.instrument}{' '}
            <span style={{ color: isLong ? 'var(--neon-green)' : 'var(--neon-red)', fontSize: 10 }}>
              {isLong ? 'LONG' : 'SHORT'}
            </span>
          </span>
          <span style={{ fontSize: 10, color: 'var(--text-secondary)' }}>
            {sizeLots.toFixed(2)} lots · Entry {formatPrice(pos.entry_price, instrument)}
          </span>
          <span style={{ fontSize: 9, color: 'var(--text-muted)' }}>
            SL: {pos.sl != null && pos.sl > 0 ? formatPrice(pos.sl, instrument) : '—'} · TP:{' '}
            {pos.tp != null && pos.tp > 0 ? formatPrice(pos.tp, instrument) : '—'}
          </span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4, flexShrink: 0 }}>
          <span style={{ fontSize: 12, fontWeight: 700, color: isPnlWin ? 'var(--neon-green)' : 'var(--neon-red)' }}>
            {isPnlWin ? '+' : ''}
            {pos.unrealized_pnl.toFixed(2)}
          </span>
          <span style={{ fontSize: 9, color: selected ? 'var(--neon-cyan)' : 'var(--text-muted)' }}>
            {selected ? 'Editing' : 'Edit'}
          </span>
        </div>
      </div>

      {selected && mode === 'manual' && legId && onModifyLeg && draft && (
        <div
          onClick={(e) => e.stopPropagation()}
          style={{
            borderTop: '1px solid rgba(255,255,255,0.06)',
            paddingTop: 8,
            display: 'flex',
            flexDirection: 'column',
            gap: 6,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 10, color: 'var(--text-secondary)', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={draft.slEnabled}
                onChange={(e) => onDraftSlToggle?.(e.target.checked)}
                style={{ accentColor: 'var(--neon-red)' }}
              />
              Stop Loss
            </label>
            {draft.slEnabled && (
              <input
                type="number"
                step={priceStep}
                value={round(draft.slPrice)}
                onChange={(e) => onDraftSlChange?.(round(Number(e.target.value)))}
                style={{
                  width: 100,
                  background: '#111827',
                  border: '1px solid var(--border-glow)',
                  padding: '3px 6px',
                  borderRadius: 4,
                  color: '#fff',
                  fontSize: 10,
                  textAlign: 'right',
                }}
              />
            )}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 10, color: 'var(--text-secondary)', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={draft.tpEnabled}
                onChange={(e) => onDraftTpToggle?.(e.target.checked)}
                style={{ accentColor: 'var(--neon-green)' }}
              />
              Take Profit
            </label>
            {draft.tpEnabled && (
              <input
                type="number"
                step={priceStep}
                value={round(draft.tpPrice)}
                onChange={(e) => onDraftTpChange?.(round(Number(e.target.value)))}
                style={{
                  width: 100,
                  background: '#111827',
                  border: '1px solid var(--border-glow)',
                  padding: '3px 6px',
                  borderRadius: 4,
                  color: '#fff',
                  fontSize: 10,
                  textAlign: 'right',
                }}
              />
            )}
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            <button
              type="button"
              onClick={handleUpdateLevels}
              style={{
                flex: 1,
                padding: '6px 8px',
                borderRadius: 4,
                border: '1px solid var(--neon-cyan)',
                background: 'rgba(0, 229, 255, 0.08)',
                color: 'var(--neon-cyan)',
                fontSize: 10,
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              Update SL / TP
            </button>
            {onCloseLeg && (
              <button
                type="button"
                onClick={handleClose}
                style={{
                  padding: '6px 10px',
                  borderRadius: 4,
                  border: '1px solid var(--neon-orange)',
                  background: 'var(--neon-orange-glow)',
                  color: 'var(--neon-orange)',
                  fontSize: 10,
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Close
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export function PortfolioState({
  sessionState,
  formatCurrency,
  instrument,
  mode,
  selectedOpenLegId = null,
  openPositionDraft,
  successMsg = null,
  onSelectOpenPosition,
  onDraftSlToggle,
  onDraftTpToggle,
  onDraftSlChange,
  onDraftTpChange,
  onCloseLeg,
  onModifyLeg,
}: PortfolioStateProps) {
  const openPositions: PositionSummary[] = sessionState?.open_positions ?? [];

  return (
    <div
      className="glass-panel"
      style={{
        padding: 14,
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        height: '100%',
        boxSizing: 'border-box',
        overflow: 'hidden',
      }}
    >
      <span style={{ fontWeight: 600, fontSize: 13, flexShrink: 0 }}>Portfolio State</span>
      {successMsg && selectedOpenLegId && (
        <div style={{ fontSize: 10, color: 'var(--neon-green)', background: 'rgba(0,230,118,0.05)', padding: 6, borderRadius: 4, flexShrink: 0 }}>
          {successMsg}
        </div>
      )}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, flexShrink: 0 }}>
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

      <div
        style={{
          marginTop: 5,
          borderTop: '1px solid rgba(255,255,255,0.04)',
          paddingTop: 8,
          flex: 1,
          minHeight: 0,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', flexShrink: 0 }}>
          OPEN POSITIONS ({openPositions.length})
        </span>
        {openPositions.length > 0 ? (
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: 6,
              marginTop: 6,
              flex: 1,
              minHeight: 0,
              overflowY: 'auto',
              paddingRight: 2,
            }}
          >
            {openPositions.map((pos, idx) => (
              <OpenPositionRow
                key={pos.leg_id ?? `${pos.instrument}-${idx}`}
                pos={pos}
                instrument={instrument}
                mode={mode}
                selected={!!pos.leg_id && pos.leg_id === selectedOpenLegId}
                draft={pos.leg_id === selectedOpenLegId ? openPositionDraft : undefined}
                onSelect={() => onSelectOpenPosition?.(pos)}
                onDraftSlToggle={onDraftSlToggle}
                onDraftTpToggle={onDraftTpToggle}
                onDraftSlChange={onDraftSlChange}
                onDraftTpChange={onDraftTpChange}
                onCloseLeg={onCloseLeg}
                onModifyLeg={onModifyLeg}
              />
            ))}
          </div>
        ) : (
          <div style={{ fontSize: 11, color: 'var(--text-muted)', textAlign: 'center', padding: 12 }}>
            No open positions.
          </div>
        )}
      </div>
    </div>
  );
}