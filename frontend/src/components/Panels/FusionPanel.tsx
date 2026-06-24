import { Shield, ChevronDown, ChevronUp } from 'lucide-react';
import { useSignalsStore } from '../../store/signals';

interface FusionPanelProps {
  instrument: string;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
}

export function FusionPanel({ instrument, isCollapsed, onToggleCollapse }: FusionPanelProps) {
  const tradeSignals = useSignalsStore((s) => s.tradeSignals);
  const technicalSignal = useSignalsStore((s) => s.technicalSignal);
  const latest = tradeSignals.find((s) => s.instrument === instrument) ?? tradeSignals[0];

  const dirColor = (dir: string) => dir === 'long' ? 'var(--neon-green)' : dir === 'short' ? 'var(--neon-red)' : 'var(--text-muted)';

  return (
    <div
      className="glass-panel"
      style={{
        padding: 16,
        display: 'flex',
        flexDirection: 'column',
        gap: isCollapsed ? 0 : 12,
        overflow: 'hidden',
        boxSizing: 'border-box'
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: isCollapsed ? 'none' : '1px solid rgba(255,255,255,0.05)', paddingBottom: isCollapsed ? 0 : 8 }}>
        <h3 style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-secondary)', margin: 0 }}>Fusion Engine</h3>
        {onToggleCollapse && (
          <button
            onClick={onToggleCollapse}
            style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', padding: 0, display: 'flex', alignItems: 'center' }}
          >
            {isCollapsed ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
          </button>
        )}
      </div>

      {!isCollapsed && (
        <>
          <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 12px', borderRadius: 8, background: 'rgba(255,255,255,0.025)', border: '1px solid rgba(255,255,255,0.05)' }}>
            <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>Technical Bias</span>
            <span style={{ fontSize: 12, fontWeight: 700, color: technicalSignal ? dirColor(technicalSignal.direction) : 'var(--text-muted)' }}>
              {technicalSignal ? technicalSignal.direction.toUpperCase() : 'Awaiting...'}
            </span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '20px 16px', borderRadius: 10, background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.08)', gap: 6 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
              <Shield size={12} color="var(--neon-cyan)" />
              <span style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 600 }}>Decision Fused</span>
            </div>
            {latest ? (
              <>
                <span style={{ fontSize: 28, fontWeight: 800, color: dirColor(latest.direction) }}>{latest.direction.toUpperCase()}</span>
                <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Confidence: <strong style={{ color: 'var(--text-primary)' }}>{Math.round(latest.confidence * 100)}%</strong></span>
                {latest.suggested_entry && <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Entry: {latest.suggested_entry.toFixed(4)}</span>}
              </>
            ) : (
              <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Waiting for decision...</span>
            )}
          </div>
        </>
      )}
    </div>
  );
}
