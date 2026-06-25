import { Radio } from 'lucide-react';
import { useSignalsStore } from '../../store/signals';

export function SignalLog() {
  const tradeSignals = useSignalsStore((s) => s.tradeSignals);

  return (
    <div className="glass-panel panel-shell" style={{ padding: 16 }}>
      <h3
        className="panel-header"
        style={{
          fontSize: 11,
          fontWeight: 600,
          textTransform: 'uppercase',
          letterSpacing: '0.08em',
          color: 'var(--text-secondary)',
          marginBottom: 12,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
        }}
      >
        <Radio size={14} color="#ff9100" /> Signal Feed
      </h3>
      <div className="panel-body panel-body-stack">
        {tradeSignals.length === 0 ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: 11, minHeight: 48 }}>
            Awaiting signals...
          </div>
        ) : (
          tradeSignals.map((sig) => (
            <div
              key={sig.signal_id}
              className="animate-fade-in"
              style={{
                padding: '8px 10px',
                borderRadius: 8,
                background: 'rgba(255,255,255,0.025)',
                border: '1px solid rgba(255,255,255,0.05)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                flexShrink: 0,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: 12, fontWeight: 700 }}>{sig.instrument}</span>
                <span
                  style={{
                    fontSize: 10,
                    fontWeight: 700,
                    padding: '2px 6px',
                    borderRadius: 4,
                    background:
                      sig.direction === 'long'
                        ? 'rgba(0,230,118,0.12)'
                        : sig.direction === 'short'
                          ? 'rgba(255,23,68,0.12)'
                          : 'rgba(255,255,255,0.05)',
                    color:
                      sig.direction === 'long'
                        ? 'var(--neon-green)'
                        : sig.direction === 'short'
                          ? 'var(--neon-red)'
                          : 'var(--text-muted)',
                  }}
                >
                  {sig.direction?.toUpperCase()}
                </span>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>
                  {Math.round(sig.confidence * 100)}%
                </div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                  {sig.timestamp ? new Date(sig.timestamp).toLocaleTimeString() : ''}
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}