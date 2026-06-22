interface Props {
  instrument: string;
  setInstrument: (v: string) => void;
  timeframe: string;
  setTimeframe: (v: string) => void;
  wsConnected: boolean;
}

const selectStyle: React.CSSProperties = {
  background: '#0e1420', color: 'var(--text-primary)', border: '1px solid rgba(255,255,255,0.1)',
  borderRadius: 6, padding: '4px 8px', fontSize: 13, fontWeight: 500, outline: 'none', cursor: 'pointer',
};

export function Header({ instrument, setInstrument, timeframe, setTimeframe, wsConnected }: Props) {
  return (
    <header style={{ height: 56, padding: '0 20px', borderBottom: '1px solid rgba(255,255,255,0.05)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'rgba(0,0,0,0.2)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <label style={{ fontSize: 9, color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 2 }}>Instrument</label>
          <select style={selectStyle} value={instrument} onChange={(e) => setInstrument(e.target.value)}>
            <option value="EURUSD">EURUSD</option>
            <option value="GBPUSD">GBPUSD</option>
            <option value="USDJPY">USDJPY</option>
            <option value="XAUUSD">XAUUSD</option>
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
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, padding: '5px 12px', borderRadius: 20, background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.06)' }}>
        <span className={`glow-indicator ${wsConnected ? 'online' : 'offline'}`} />
        WS: {wsConnected ? 'Live' : 'Offline'}
      </div>
    </header>
  );
}
