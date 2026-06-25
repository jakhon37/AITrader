import { useState } from 'react';
import { Settings, ChevronDown, ChevronUp } from 'lucide-react';
import { getInstrumentConfig, putInstrumentConfig } from '../../api/client';

interface Config { fundamental_weight: number; technical_weight: number; max_position_lots: number; news_halt_minutes: number; }

interface ConfigEditorProps {
  instrument: string;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
}

export function ConfigEditor({ instrument, isCollapsed, onToggleCollapse }: ConfigEditorProps) {
  const [config, setConfig] = useState<Config>({ fundamental_weight: 0.3, technical_weight: 0.7, max_position_lots: 1.0, news_halt_minutes: 30 });
  const [msg, setMsg] = useState('');

  const load = () => {
    getInstrumentConfig(instrument)
      .then((data: Config) => { if (data && !('detail' in (data as object))) setConfig(data); })
      .catch(() => {});
  };

  const save = (e: React.FormEvent) => {
    e.preventDefault();
    setMsg('Saving...');
    putInstrumentConfig(instrument, config)
      .then(() => { setMsg('Saved!'); setTimeout(() => setMsg(''), 3000); })
      .catch(async (err: unknown) => {
        let detail = 'Failed.';
        if (err instanceof Error && err.message) {
          detail = err.message;
        }
        setMsg(detail);
      });
  };

  const inputStyle: React.CSSProperties = { background: '#0e1420', color: 'white', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 4, padding: '3px 6px', width: 60, textAlign: 'center' };
  const rowStyle: React.CSSProperties = { display: 'flex', justifyContent: 'space-between', alignItems: 'center' };

  return (
    <div
      className={`glass-panel ${isCollapsed ? '' : 'panel-shell'}`}
      style={{ padding: 16, gap: isCollapsed ? 0 : 8 }}
    >
      <div className="panel-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%', marginBottom: isCollapsed ? 0 : 4 }}>
        <h3 style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-secondary)', margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
          <Settings size={14} color="var(--neon-cyan)" /> Config
        </h3>
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
        <form onSubmit={save} className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 8, fontSize: 12 }} onClick={load}>
          <div style={rowStyle}><label style={{ color: 'var(--text-secondary)' }}>Fund. Weight</label><input style={inputStyle} type="number" step={0.05} min={0} max={1} value={config.fundamental_weight} onChange={(e) => setConfig({ ...config, fundamental_weight: parseFloat(e.target.value) })} /></div>
          <div style={rowStyle}><label style={{ color: 'var(--text-secondary)' }}>Tech. Weight</label><input style={inputStyle} type="number" step={0.05} min={0} max={1} value={config.technical_weight} onChange={(e) => setConfig({ ...config, technical_weight: parseFloat(e.target.value) })} /></div>
          <div style={rowStyle}><label style={{ color: 'var(--text-secondary)' }}>Max Lots</label><input style={inputStyle} type="number" step={0.1} min={0.1} value={config.max_position_lots} onChange={(e) => setConfig({ ...config, max_position_lots: parseFloat(e.target.value) })} /></div>
          <button type="submit" style={{ marginTop: 8, padding: '7px 0', background: 'rgba(0,229,255,0.15)', border: '1px solid rgba(0,229,255,0.35)', borderRadius: 6, color: 'var(--neon-cyan)', fontWeight: 700, cursor: 'pointer', fontSize: 12, flexShrink: 0 }}>Apply</button>
          {msg && <p style={{ textAlign: 'center', fontSize: 10, color: 'var(--neon-cyan)', margin: 0, flexShrink: 0 }}>{msg}</p>}
        </form>
      )}
    </div>
  );
}