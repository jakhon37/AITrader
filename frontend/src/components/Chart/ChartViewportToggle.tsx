import type { ChartViewportMode } from './utils';

interface Props {
  mode: ChartViewportMode;
  onChange: (mode: ChartViewportMode) => void;
}

export function ChartViewportToggle({ mode, onChange }: Props) {
  return (
    <div
      style={{
        display: 'flex',
        background: '#111827',
        borderRadius: 6,
        padding: 2,
        border: '1px solid var(--border-glow)',
      }}
      title="Chart zoom when switching timeframes"
    >
      {([
        { id: 'auto' as const, label: 'Auto Zoom' },
        { id: 'fit-all' as const, label: 'Fit All' },
      ]).map((opt) => (
        <button
          key={opt.id}
          onClick={() => onChange(opt.id)}
          style={{
            background: mode === opt.id ? 'var(--neon-cyan-glow)' : 'transparent',
            border: 'none',
            color: mode === opt.id ? '#fff' : 'var(--text-secondary)',
            padding: '4px 8px',
            borderRadius: 4,
            fontSize: 11,
            fontWeight: 600,
            cursor: 'pointer',
            transition: 'all 0.2s ease',
            whiteSpace: 'nowrap',
          }}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}