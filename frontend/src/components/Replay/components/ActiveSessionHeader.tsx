import { Play, Pause, Square, Activity, Layout } from 'lucide-react';

interface ActiveSessionHeaderProps {
  instrument: string;
  timeframe: string;
  mode: string;
  currentTime: string | null;
  formatDateTime: (isoString: string | null) => string;
  status: string;
  handlePause: () => void;
  handleResume: () => void;
  speed: number;
  onSpeedChange: (speed: number) => void;
  calculateIndicators: boolean;
  onIndicatorsChange: (checked: boolean) => void;
  handleStop: () => void;
  sidebarHidden?: boolean;
  rightPanelHidden?: boolean;
  onToggleRightPanel?: () => void;
}

export function ActiveSessionHeader({
  instrument,
  timeframe,
  mode,
  currentTime,
  formatDateTime,
  status,
  handlePause,
  handleResume,
  speed,
  onSpeedChange,
  calculateIndicators,
  onIndicatorsChange,
  handleStop,
  sidebarHidden,
  rightPanelHidden,
  onToggleRightPanel,
}: ActiveSessionHeaderProps) {
  return (
    <header style={{ 
      display: 'flex', 
      justifyContent: 'space-between', 
      alignItems: 'center', 
      padding: sidebarHidden ? '0 20px 0 64px' : '0 20px', 
      background: 'rgba(7, 9, 14, 0.8)', 
      borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
      zIndex: 10,
      transition: 'padding-left 0.3s cubic-bezier(0.16, 1, 0.3, 1)',
      height: 56,
      boxSizing: 'border-box'
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
        <span style={{ fontSize: 16, fontWeight: 700, color: 'var(--neon-cyan)', display: 'flex', alignItems: 'center', gap: 6 }}>
          <Activity size={18} />
          REPLAY STUDIO
        </span>
        <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
          Instrument: <strong style={{ color: '#fff' }}>{instrument}</strong>
        </span>
        <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
          Timeframe: <strong style={{ color: '#fff' }}>{timeframe}</strong>
        </span>
        <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
          Mode: <strong style={{ color: '#fff' }}>{mode.toUpperCase()}</strong>
        </span>
        <span style={{ fontSize: 12, background: 'rgba(255,255,255,0.06)', padding: '3px 8px', borderRadius: 4, color: 'var(--text-secondary)' }}>
          Virtual Clock: <strong style={{ color: 'var(--neon-cyan)', fontFamily: 'monospace' }}>{formatDateTime(currentTime)}</strong>
        </span>
      </div>

      {/* Buttons Control Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        {status === 'running' ? (
          <button 
            onClick={handlePause}
            style={{ display: 'flex', alignItems: 'center', gap: 6, background: '#1e2937', border: '1px solid var(--border-glow)', padding: '6px 12px', borderRadius: 6, cursor: 'pointer', color: '#fff', fontSize: 13 }}
          >
            <Pause size={14} />
            Pause
          </button>
        ) : (
          <button 
            onClick={handleResume}
            style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'var(--neon-cyan-glow)', border: '1px solid var(--neon-cyan)', padding: '6px 12px', borderRadius: 6, cursor: 'pointer', color: '#fff', fontSize: 13 }}
          >
            <Play size={14} />
            Play
          </button>
        )}

        {/* Dynamic Speed Selector */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, background: '#111827', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 6, padding: '5px 10px' }}>
          <span style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 600 }}>SPEED:</span>
          <select
            value={speed}
            onChange={(e) => onSpeedChange(Number(e.target.value))}
            style={{
              background: 'transparent',
              border: 'none',
              color: '#fff',
              fontSize: 12,
              cursor: 'pointer',
              outline: 'none',
            }}
          >
            {[1, 3, 5, 10, 20, 50, 100].map((s) => (
              <option key={s} value={s}>{s}x</option>
            ))}
          </select>
        </div>

        {/* Dynamic Indicators Toggle */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, background: '#111827', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 6, padding: '5px 10px' }}>
          <span style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 600 }}>INDICATORS:</span>
          <input 
            type="checkbox"
            checked={calculateIndicators}
            onChange={(e) => onIndicatorsChange(e.target.checked)}
            style={{ cursor: 'pointer', accentColor: 'var(--neon-cyan)', width: 14, height: 14 }}
          />
        </div>

        {/* Status Badge */}
        <span style={{ 
          fontSize: 9, 
          fontWeight: 700, 
          textTransform: 'uppercase', 
          color: status === 'running' ? 'var(--neon-green)' : status === 'paused' ? 'var(--neon-cyan)' : '#ff5252',
          background: status === 'running' ? 'rgba(0,230,118,0.1)' : status === 'paused' ? 'rgba(0,229,255,0.1)' : 'rgba(255,23,68,0.1)',
          padding: '4px 8px',
          borderRadius: 4,
          letterSpacing: '0.05em'
        }}>
          {status}
        </span>

        <button 
          onClick={handleStop}
          style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(255, 23, 68, 0.1)', border: '1px solid var(--neon-red)', padding: '6px 12px', borderRadius: 6, cursor: 'pointer', color: '#ff5252', fontSize: 13 }}
        >
          <Square size={12} fill="#ff5252" />
          End Session
        </button>

        {onToggleRightPanel && (
          <button
            onClick={onToggleRightPanel}
            title={rightPanelHidden ? "Show Right Dashboard" : "Hide Right Dashboard"}
            style={{
              background: rightPanelHidden ? 'rgba(0,229,255,0.1)' : 'transparent',
              border: `1px solid ${rightPanelHidden ? 'var(--neon-cyan)' : 'rgba(255,255,255,0.15)'}`,
              color: rightPanelHidden ? 'var(--neon-cyan)' : 'var(--text-secondary)',
              cursor: 'pointer',
              padding: '6px',
              borderRadius: '6px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              transition: 'all 0.2s',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.color = '#fff';
              e.currentTarget.style.borderColor = 'var(--neon-cyan)';
              e.currentTarget.style.background = 'var(--neon-cyan-glow)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.color = rightPanelHidden ? 'var(--neon-cyan)' : 'var(--text-secondary)';
              e.currentTarget.style.borderColor = rightPanelHidden ? 'var(--neon-cyan)' : 'rgba(255,255,255,0.15)';
              e.currentTarget.style.background = rightPanelHidden ? 'rgba(0,229,255,0.1)' : 'transparent';
            }}
          >
            <Layout size={16} />
          </button>
        )}
      </div>
    </header>
  );
}
