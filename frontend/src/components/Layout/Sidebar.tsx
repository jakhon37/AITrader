import { Activity, PlayCircle } from 'lucide-react';
import { useSignalsStore } from '../../store/signals';
import { Link, useLocation } from 'react-router-dom';

export function Sidebar() {
  const { healthStatus } = useSignalsStore();
  const location = useLocation();

  const navItem = (to: string, icon: React.ReactNode, label: string) => {
    const active = location.pathname === to;
    return (
      <Link to={to} style={{ textDecoration: 'none' }}>
        <button style={{
          display: 'flex', alignItems: 'center', gap: 12, padding: '10px 16px', borderRadius: 8, width: '100%',
          textAlign: 'left', fontSize: 13, fontWeight: 500, cursor: 'pointer', border: 'none', transition: 'all 0.2s',
          background: active ? 'rgba(0,229,255,0.08)' : 'transparent',
          color: active ? 'var(--neon-cyan)' : 'var(--text-muted)',
          borderLeft: active ? '2px solid var(--neon-cyan)' : '2px solid transparent',
        }}>
          {icon} {label}
        </button>
      </Link>
    );
  };

  return (
    <aside className="glass-panel" style={{ margin: 12, display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
      <div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '20px 20px 16px', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
          <Activity size={20} color="var(--neon-cyan)" />
          <span style={{ fontWeight: 700, fontSize: 16, letterSpacing: '0.04em' }}>AITrader</span>
        </div>
        <nav style={{ padding: '12px 8px', display: 'flex', flexDirection: 'column', gap: 4 }}>
          {navItem('/', <Activity size={16} />, 'Terminal')}
          {navItem('/replay', <PlayCircle size={16} />, 'Replay Studio')}
        </nav>
      </div>

      <div style={{ padding: '16px 20px', borderTop: '1px solid rgba(255,255,255,0.05)', background: 'rgba(0,0,0,0.15)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Platform</span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, fontWeight: 600 }}>
            <span className={`glow-indicator ${healthStatus.status === 'ok' ? 'online' : healthStatus.status === 'degraded' ? 'warn' : 'offline'}`} />
            {healthStatus.status.toUpperCase()}
          </span>
        </div>
        {Object.entries(healthStatus.divisions).map(([key, div]) => (
          <div key={key} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'var(--text-muted)', padding: '2px 0' }}>
            <span>{key}</span>
            <span style={{ color: div.status === 'ok' ? 'var(--neon-green)' : 'var(--neon-red)' }}>{div.status.toUpperCase()}</span>
          </div>
        ))}
      </div>
    </aside>
  );
}
