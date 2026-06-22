import { Globe } from 'lucide-react';
import { useSignalsStore } from '../../store/signals';

export function NewsFeed() {
  const fundamentalSignals = useSignalsStore((s) => s.fundamentalSignals);

  const sentimentColor = (score: number) => score >= 0.15 ? 'var(--neon-green)' : score <= -0.15 ? 'var(--neon-red)' : 'var(--text-muted)';
  const sentimentLabel = (score: number) => score >= 0.15 ? 'BULLISH' : score <= -0.15 ? 'BEARISH' : 'NEUTRAL';

  return (
    <div className="glass-panel" style={{ padding: 16, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <h3 style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-secondary)', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
        <Globe size={14} color="var(--neon-cyan)" /> News Sentinel
      </h3>
      <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 10 }}>
        {fundamentalSignals.length === 0 ? (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: 11 }}>No news events yet.</div>
        ) : fundamentalSignals.map((sig) => (
          <div key={sig.signal_id} style={{ paddingBottom: 10, borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
              <span style={{ fontSize: 12, fontWeight: 700 }}>{sig.instrument}</span>
              <span style={{ fontSize: 11, fontWeight: 700, color: sentimentColor(sig.sentiment_score) }}>{sentimentLabel(sig.sentiment_score)}</span>
            </div>
            <p style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.5, margin: 0, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>{sig.source_headline}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
