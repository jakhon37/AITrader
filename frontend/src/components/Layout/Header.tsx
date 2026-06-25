import { Layout } from 'lucide-react';

interface Props {
  instruments?: string[];
  instrument: string;
  setInstrument: (v: string) => void;
  timeframe: string;
  setTimeframe: (v: string) => void;
  wsConnected: boolean;
  sidebarHidden?: boolean;
  rightPanelHidden?: boolean;
  onToggleRightPanel?: () => void;
}

const selectStyle: React.CSSProperties = {
  background: '#0e1420', color: 'var(--text-primary)', border: '1px solid rgba(255,255,255,0.1)',
  borderRadius: 6, padding: '4px 8px', fontSize: 13, fontWeight: 500, outline: 'none', cursor: 'pointer',
};

const DEFAULT_INSTRUMENTS = ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD'];

export function Header({ instruments = DEFAULT_INSTRUMENTS, instrument, setInstrument, timeframe, setTimeframe, wsConnected, sidebarHidden, rightPanelHidden, onToggleRightPanel }: Props) {
  return (
    <header
      style={{
        height: 56,
        padding: sidebarHidden ? '0 20px 0 64px' : '0 20px',
        borderBottom: '1px solid rgba(255,255,255,0.05)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        background: 'rgba(0,0,0,0.2)',
        transition: 'padding-left 0.3s cubic-bezier(0.16, 1, 0.3, 1)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <label style={{ fontSize: 9, color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 2 }}>Instrument</label>
          <select style={selectStyle} value={instrument} onChange={(e) => setInstrument(e.target.value)}>
            {instruments.map((sym) => (
              <option key={sym} value={sym}>{sym}</option>
            ))}
          </select>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <label style={{ fontSize: 9, color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 2 }}>Timeframe</label>
          <select style={selectStyle} value={timeframe} onChange={(e) => setTimeframe(e.target.value)}>
            <option value="1m">1m</option><option value="5m">5m</option><option value="15m">15m</option>
            <option value="30m">30m</option><option value="1h">1h</option><option value="4h">4h</option><option value="1d">1d</option>
          </select>
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, padding: '5px 12px', borderRadius: 20, background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.06)' }}>
          <span className={`glow-indicator ${wsConnected ? 'online' : 'offline'}`} />
          WS: {wsConnected ? 'Live' : 'Offline'}
        </div>
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
