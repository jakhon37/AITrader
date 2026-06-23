import { Routes, Route } from 'react-router-dom';
import { Sidebar } from './components/Layout/Sidebar';
import { TradingTerminal } from './components/Layout/TradingTerminal';
import { ReplayPage } from './components/Replay/ReplayPage';
import { useWebSocket } from './hooks/useWebSocket';
import { useState } from 'react';
import { Menu } from 'lucide-react';

export default function App() {
  useWebSocket();
  const [sidebarHidden, setSidebarHidden] = useState(() => {
    const saved = localStorage.getItem('sidebar_hidden');
    return saved === 'true';
  });

  const handleToggleSidebar = () => {
    setSidebarHidden((prev) => {
      const next = !prev;
      localStorage.setItem('sidebar_hidden', String(next));
      return next;
    });
  };

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: sidebarHidden ? '0px 1fr' : '260px 1fr',
        height: '100vh',
        width: '100vw',
        transition: 'grid-template-columns 0.3s cubic-bezier(0.16, 1, 0.3, 1)',
        overflow: 'hidden',
        position: 'relative',
      }}
    >
      <Sidebar isHidden={sidebarHidden} onToggle={handleToggleSidebar} />
      <main style={{ overflow: 'hidden', display: 'flex', flexDirection: 'column', position: 'relative' }}>
        {sidebarHidden && (
          <button
            onClick={handleToggleSidebar}
            title="Show Sidebar Navigation"
            style={{
              position: 'absolute',
              left: '16px',
              top: '12px',
              zIndex: 99999, // Render above charts but below full screen overlay
              background: 'rgba(14, 20, 32, 0.85)',
              border: '1px solid var(--border-glow)',
              color: 'var(--neon-cyan)',
              width: '32px',
              height: '32px',
              borderRadius: '8px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
              backdropFilter: 'blur(16px)',
              WebkitBackdropFilter: 'blur(16px)',
              transition: 'all 0.2s',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = 'var(--neon-cyan)';
              e.currentTarget.style.color = '#fff';
              e.currentTarget.style.boxShadow = '0 0 10px var(--neon-cyan-glow)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = 'var(--border-glow)';
              e.currentTarget.style.color = 'var(--neon-cyan)';
              e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.5)';
            }}
          >
            <Menu size={16} />
          </button>
        )}
        <Routes>
          <Route path="/" element={<TradingTerminal sidebarHidden={sidebarHidden} />} />
          <Route path="/replay" element={<ReplayPage sidebarHidden={sidebarHidden} />} />
        </Routes>
      </main>
    </div>
  );
}
