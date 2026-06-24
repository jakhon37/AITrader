import { MousePointer, TrendingUp, Square, Eraser, Trash2, ChevronLeft, ChevronRight, ArrowUpDown, Percent, Slash } from 'lucide-react';
import { useState, type CSSProperties } from 'react';

interface DrawingToolbarProps {
  activeTool: 'select' | 'line' | 'box' | 'polyline' | 'eraser' | 'position' | 'fibonacci';
  setActiveTool: (tool: 'select' | 'line' | 'box' | 'polyline' | 'eraser' | 'position' | 'fibonacci') => void;
  onClear: () => void;
}

const TOOL_BTN_BASE: CSSProperties = {
  border: 'none',
  borderRadius: '8px',
  cursor: 'pointer',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: '36px',
  height: '36px',
  transition: 'background 0.15s ease, color 0.15s ease, box-shadow 0.15s ease',
  backdropFilter: 'blur(10px)',
  WebkitBackdropFilter: 'blur(10px)',
};

function toolBtnStyle(active: boolean): CSSProperties {
  return {
    ...TOOL_BTN_BASE,
    background: active ? 'rgba(0, 229, 255, 0.2)' : 'rgba(14, 20, 32, 0.48)',
    color: active ? 'var(--neon-cyan)' : 'var(--text-secondary)',
    boxShadow: active ? '0 2px 10px rgba(0, 229, 255, 0.22)' : '0 1px 4px rgba(0, 0, 0, 0.18)',
  };
}

const CHROME_BTN: CSSProperties = {
  ...TOOL_BTN_BASE,
  background: 'rgba(14, 20, 32, 0.48)',
  color: 'var(--text-muted)',
  boxShadow: '0 1px 4px rgba(0, 0, 0, 0.18)',
};

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
        type="button"
        onClick={() => setIsCollapsed(false)}
        title="Show Drawing Tools"
        style={{
          ...CHROME_BTN,
          position: 'absolute',
          left: '12px',
          top: '12px',
          zIndex: 1000000,
          color: 'var(--neon-cyan)',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.background = 'rgba(0, 229, 255, 0.15)';
          e.currentTarget.style.boxShadow = '0 2px 10px rgba(0, 229, 255, 0.2)';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.background = 'rgba(14, 20, 32, 0.48)';
          e.currentTarget.style.boxShadow = '0 1px 4px rgba(0, 0, 0, 0.18)';
        }}
      >
        <ChevronRight size={18} />
      </button>
    );
  }

  return (
    <div
      style={{
        position: 'absolute',
        left: '12px',
        top: '12px',
        zIndex: 1000000,
        display: 'flex',
        flexDirection: 'column',
        gap: '6px',
        alignItems: 'center',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
        <span
          style={{
            fontSize: '9px',
            fontWeight: 700,
            letterSpacing: '0.08em',
            color: 'var(--text-muted)',
            padding: '4px 6px',
            borderRadius: '6px',
            background: 'rgba(14, 20, 32, 0.4)',
            backdropFilter: 'blur(8px)',
            WebkitBackdropFilter: 'blur(8px)',
          }}
        >
          DRAW
        </span>
        <button
          type="button"
          onClick={() => setIsCollapsed(true)}
          title="Hide Drawing Tools"
          style={{
            ...CHROME_BTN,
            width: '28px',
            height: '28px',
            borderRadius: '6px',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.color = '#fff';
            e.currentTarget.style.background = 'rgba(14, 20, 32, 0.72)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.color = 'var(--text-muted)';
            e.currentTarget.style.background = 'rgba(14, 20, 32, 0.48)';
          }}
        >
          <ChevronLeft size={14} />
        </button>
      </div>

      {tools.map((t) => {
        const Icon = t.icon;
        const isActive = activeTool === t.id;
        return (
          <button
            key={t.id}
            type="button"
            title={t.label}
            onClick={() => setActiveTool(t.id)}
            style={toolBtnStyle(isActive)}
            onMouseEnter={(e) => {
              if (!isActive) {
                e.currentTarget.style.color = '#fff';
                e.currentTarget.style.background = 'rgba(14, 20, 32, 0.68)';
              }
            }}
            onMouseLeave={(e) => {
              if (!isActive) {
                e.currentTarget.style.color = 'var(--text-secondary)';
                e.currentTarget.style.background = 'rgba(14, 20, 32, 0.48)';
                e.currentTarget.style.boxShadow = '0 1px 4px rgba(0, 0, 0, 0.18)';
              }
            }}
          >
            <Icon size={18} />
          </button>
        );
      })}

      <button
        type="button"
        title="Clear All Drawings"
        onClick={onClear}
        style={{
          ...CHROME_BTN,
          marginTop: '2px',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.color = 'var(--neon-red)';
          e.currentTarget.style.background = 'rgba(255, 23, 68, 0.35)';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.color = 'var(--text-muted)';
          e.currentTarget.style.background = 'rgba(14, 20, 32, 0.48)';
        }}
      >
        <Trash2 size={18} />
      </button>
    </div>
  );
}