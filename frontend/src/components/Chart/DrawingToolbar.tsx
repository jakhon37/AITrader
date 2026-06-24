import { MousePointer, TrendingUp, Square, Eraser, Trash2, ChevronLeft, ChevronRight, ArrowUpDown, Percent, Slash } from 'lucide-react';
import { useState } from 'react';

interface DrawingToolbarProps {
  activeTool: 'select' | 'line' | 'box' | 'polyline' | 'eraser' | 'position' | 'fibonacci';
  setActiveTool: (tool: 'select' | 'line' | 'box' | 'polyline' | 'eraser' | 'position' | 'fibonacci') => void;
  onClear: () => void;
}

export function DrawingToolbar({
  activeTool,
  setActiveTool,
  onClear,
}: DrawingToolbarProps) {
  const [isCollapsed, setIsCollapsed] = useState(false);

  const tools = [
    { id: 'select', icon: MousePointer, label: 'Select' },
    { id: 'line', icon: Slash, label: 'Trend Line' },
    { id: 'box', icon: Square, label: 'Box Zone' },
    { id: 'polyline', icon: TrendingUp, label: 'Polyline Path' },
    { id: 'fibonacci', icon: Percent, label: 'Fib Retracement' },
    { id: 'position', icon: ArrowUpDown, label: 'Risk/Reward Position' },
    { id: 'eraser', icon: Eraser, label: 'Delete Drawing' },
  ] as const;


  if (isCollapsed) {
    return (
      <button
        onClick={() => setIsCollapsed(false)}
        title="Show Drawing Tools"
        style={{
          position: 'absolute',
          left: '12px',
          top: '12px',
          zIndex: 1000000,
          background: 'rgba(14, 20, 32, 0.85)',
          border: '1px solid var(--border-glow)',
          color: 'var(--neon-cyan)',
          cursor: 'pointer',
          padding: '10px',
          borderRadius: '10px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          boxShadow: '0 4px 20px rgba(0,0,0,0.5)',
          backdropFilter: 'blur(16px)',
          WebkitBackdropFilter: 'blur(16px)',
          transition: 'all 0.2s ease',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.borderColor = 'var(--neon-cyan)';
          e.currentTarget.style.boxShadow = '0 0 10px var(--neon-cyan-glow)';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.borderColor = 'var(--border-glow)';
          e.currentTarget.style.boxShadow = '0 4px 20px rgba(0,0,0,0.5)';
        }}
      >
        <ChevronRight size={18} />
      </button>
    );
  }

  return (
    <div
      className="glass-panel"
      style={{
        position: 'absolute',
        left: '12px',
        top: '12px',
        zIndex: 1000000,
        display: 'flex',
        flexDirection: 'column',
        gap: '12px',
        padding: '12px',
        alignItems: 'center',
        width: '120px',
        boxSizing: 'border-box',
        background: 'rgba(14, 20, 32, 0.85)', // translucent/opacity box background
        boxShadow: '0 8px 32px 0 rgba(0, 0, 0, 0.5)',
        backdropFilter: 'blur(16px)',
        WebkitBackdropFilter: 'blur(16px)',
        transition: 'opacity 0.2s ease, transform 0.2s ease',
      }}
    >
      {/* 0. Collapse Header */}
      <div style={{ display: 'flex', width: '100%', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: '10px', fontWeight: 700, letterSpacing: '0.05em', color: 'var(--text-muted)' }}>DRAW</span>
        <button
          onClick={() => setIsCollapsed(true)}
          title="Hide Drawing Tools"
          style={{
            background: 'transparent',
            border: 'none',
            color: 'var(--text-muted)',
            cursor: 'pointer',
            padding: '2px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            borderRadius: '4px',
            transition: 'color 0.2s',
          }}
          onMouseEnter={(e) => e.currentTarget.style.color = '#fff'}
          onMouseLeave={(e) => e.currentTarget.style.color = 'var(--text-muted)'}
        >
          <ChevronLeft size={16} />
        </button>
      </div>

      <div style={{ width: '100%', height: '1px', background: 'rgba(255,255,255,0.08)' }} />
      {/* 1. Tools Section */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', width: '100%', alignItems: 'center' }}>
        {tools.map((t) => {
          const Icon = t.icon;
          const isActive = activeTool === t.id;
          return (
            <button
              key={t.id}
              title={t.label}
              onClick={() => setActiveTool(t.id)}
              style={{
                background: isActive ? 'var(--neon-cyan-glow)' : 'transparent',
                border: `1px solid ${isActive ? 'var(--neon-cyan)' : 'transparent'}`,
                color: isActive ? 'var(--neon-cyan)' : 'var(--text-secondary)',
                cursor: 'pointer',
                padding: '8px',
                borderRadius: '8px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                transition: 'all 0.2s ease',
                width: '36px',
                height: '36px',
              }}
              onMouseEnter={(e) => {
                if (!isActive) {
                  e.currentTarget.style.color = '#fff';
                  e.currentTarget.style.background = 'rgba(255,255,255,0.03)';
                }
              }}
              onMouseLeave={(e) => {
                if (!isActive) {
                  e.currentTarget.style.color = 'var(--text-secondary)';
                  e.currentTarget.style.background = 'transparent';
                }
              }}
            >
              <Icon size={18} />
            </button>
          );
        })}
      </div>

      <div style={{ width: '100%', height: '1px', background: 'rgba(255,255,255,0.08)' }} />

      {/* 6. Action / Clear Button */}
      <button
        title="Clear All Drawings"
        onClick={onClear}
        style={{
          background: 'transparent',
          border: 'none',
          color: 'var(--text-muted)',
          cursor: 'pointer',
          padding: '8px',
          borderRadius: '8px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          transition: 'all 0.2s ease',
          width: '36px',
          height: '36px',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.color = 'var(--neon-red)';
          e.currentTarget.style.background = 'var(--neon-red-glow)';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.color = 'var(--text-muted)';
          e.currentTarget.style.background = 'transparent';
        }}
      >
        <Trash2 size={18} />
      </button>
    </div>
  );
}
