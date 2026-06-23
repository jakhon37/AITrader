import { MousePointer, TrendingUp, Square, PenTool, Eraser, Trash2, ChevronLeft, ChevronRight } from 'lucide-react';
import { useState } from 'react';

interface DrawingToolbarProps {
  activeTool: 'select' | 'line' | 'box' | 'polyline' | 'eraser';
  setActiveTool: (tool: 'select' | 'line' | 'box' | 'polyline' | 'eraser') => void;
  onClear: () => void;
  currentColor: string;
  setCurrentColor: (color: string) => void;
  currentLineWidth: number;
  setCurrentLineWidth: (width: number) => void;
  fillBox: boolean;
  setFillBox: (fill: boolean) => void;
  currentOpacity: number;
  setCurrentOpacity: (opacity: number) => void;
  showFillOption?: boolean;
}

export function DrawingToolbar({
  activeTool,
  setActiveTool,
  onClear,
  currentColor,
  setCurrentColor,
  currentLineWidth,
  setCurrentLineWidth,
  fillBox,
  setFillBox,
  currentOpacity,
  setCurrentOpacity,
  showFillOption = true,
}: DrawingToolbarProps) {
  const [isCollapsed, setIsCollapsed] = useState(false);

  const tools = [
    { id: 'select', icon: MousePointer, label: 'Select' },
    { id: 'line', icon: TrendingUp, label: 'Trend Line' },
    { id: 'box', icon: Square, label: 'Box Zone' },
    { id: 'polyline', icon: PenTool, label: 'Polyline Path' },
    { id: 'eraser', icon: Eraser, label: 'Delete Drawing' },
  ] as const;

  const colors = [
    '#00e5ff', // Cyan
    '#00e676', // Green
    '#ff9100', // Orange
    '#ff1744', // Red
    '#ffea00', // Yellow
    '#ffffff', // White
  ];

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

      {/* 2. Color Selection */}
      <div style={{ width: '100%' }}>
        <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '6px', textAlign: 'center', fontWeight: 600 }}>
          Color
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '6px', justifyItems: 'center' }}>
          {colors.map((c) => (
            <div
              key={c}
              className={`color-dot ${currentColor === c ? 'active' : ''}`}
              style={{ backgroundColor: c, color: c }}
              onClick={() => setCurrentColor(c)}
              title={c}
            />
          ))}
        </div>
      </div>

      <div style={{ width: '100%', height: '1px', background: 'rgba(255,255,255,0.08)' }} />

      {/* 3. Line Thickness Selection */}
      <div style={{ width: '100%' }}>
        <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '6px', textAlign: 'center', fontWeight: 600 }}>
          Size
        </div>
        <div style={{ display: 'flex', gap: '4px', justifyContent: 'center' }}>
          {[1, 2, 3, 4].map((w) => {
            const isActive = currentLineWidth === w;
            return (
              <button
                key={w}
                onClick={() => setCurrentLineWidth(w)}
                style={{
                  background: isActive ? 'var(--neon-cyan-glow)' : 'transparent',
                  border: `1px solid ${isActive ? 'var(--neon-cyan)' : 'transparent'}`,
                  color: isActive ? 'var(--neon-cyan)' : 'var(--text-secondary)',
                  borderRadius: '4px',
                  padding: '2px 6px',
                  fontSize: '11px',
                  cursor: 'pointer',
                  fontWeight: isActive ? 600 : 400,
                  transition: 'all 0.15s ease',
                }}
              >
                {w}px
              </button>
            );
          })}
        </div>
      </div>

      {showFillOption && (
        <>
          <div style={{ width: '100%', height: '1px', background: 'rgba(255,255,255,0.08)' }} />

          {/* 4. Box Fill Toggle */}
          <div style={{ width: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
            <label
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                fontSize: '11px',
                color: 'var(--text-secondary)',
                cursor: 'pointer',
                userSelect: 'none',
              }}
            >
              <input
                type="checkbox"
                checked={fillBox}
                onChange={(e) => setFillBox(e.target.checked)}
                style={{
                  cursor: 'pointer',
                  accentColor: 'var(--neon-cyan)',
                }}
              />
              Fill Box
            </label>
          </div>
        </>
      )}

      <div style={{ width: '100%', height: '1px', background: 'rgba(255,255,255,0.08)' }} />

      {/* 5. Opacity Selection */}
      <div style={{ width: '100%' }}>
        <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '6px', textAlign: 'center', fontWeight: 600 }}>
          Opacity ({Math.round(currentOpacity * 100)}%)
        </div>
        <input
          type="range"
          min="0.1"
          max="1.0"
          step="0.1"
          value={currentOpacity}
          onChange={(e) => setCurrentOpacity(parseFloat(e.target.value))}
          className="drawing-slider"
          style={{ width: '100%', boxSizing: 'border-box' }}
        />
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
