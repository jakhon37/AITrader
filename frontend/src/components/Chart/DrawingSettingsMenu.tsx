import { useState, type CSSProperties } from 'react';
import { Trash2, ChevronDown, Plus, X } from 'lucide-react';
import type { Drawing } from './drawingTypes';
import type { DropdownDirection } from './drawingUtils';

interface DrawingSettingsMenuProps {
  selectedDrawing: Drawing;
  position: { top: number; left: number };
  dropdownDirection: DropdownDirection;
  onUpdateColor: (color: string) => void;
  onUpdateLineWidth: (width: number) => void;
  onUpdateFill: (fill: boolean) => void;
  onUpdateOpacity: (opacity: number) => void;
  onUpdateExtendRight?: (extend: boolean) => void;
  onUpdateFibLevels?: (levels: number[]) => void;
  onDelete: () => void;
}

const DROPDOWN_PANEL_BASE: CSSProperties = {
  position: 'absolute',
  left: 0,
  background: 'rgba(14, 20, 32, 0.95)',
  border: '1px solid var(--border-glow)',
  borderRadius: '8px',
  boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
  zIndex: 1000002,
};

function dropdownPanelStyle(direction: DropdownDirection): CSSProperties {
  return direction === 'down'
    ? { ...DROPDOWN_PANEL_BASE, top: 'calc(100% + 8px)' }
    : { ...DROPDOWN_PANEL_BASE, bottom: 'calc(100% + 8px)' };
}

export function DrawingSettingsMenu({
  selectedDrawing,
  position,
  dropdownDirection,
  onUpdateColor,
  onUpdateLineWidth,
  onUpdateFill,
  onUpdateOpacity,
  onUpdateExtendRight,
  onUpdateFibLevels,
  onDelete,
}: DrawingSettingsMenuProps) {
  const [activeDropdown, setActiveDropdown] = useState<'color' | 'width' | 'opacity' | 'options' | 'levels' | null>(null);
  const [newLevelInput, setNewLevelInput] = useState('');

  const colors = [
    // Neons / Brights
    '#00e5ff', '#00e676', '#ffea00', '#ff9100', '#ff1744',
    // Rich Colors
    '#2979ff', '#00bfa5', '#76ff03', '#ffd600', '#ff5722',
    // Pastels / Soft
    '#81d4fa', '#a5d6a7', '#fff59d', '#ffcc80', '#ef9a9a',
    // Purples & Neutrals
    '#d500f9', '#ff4081', '#ffffff', '#90a4ae', '#37474f',
  ];

  const currentLevels = selectedDrawing.fibLevels || [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0, 1.618, 2.618, 3.618, 4.236];

  const handleAddLevel = () => {
    const val = parseFloat(newLevelInput);
    if (!isNaN(val) && onUpdateFibLevels) {
      if (!currentLevels.includes(val)) {
        const nextLevels = [...currentLevels, val].sort((a, b) => a - b);
        onUpdateFibLevels(nextLevels);
      }
      setNewLevelInput('');
    }
  };

  const handleRemoveLevel = (ratio: number) => {
    if (!onUpdateFibLevels) return;
    if (currentLevels.length <= 1) return;
    onUpdateFibLevels(currentLevels.filter((l) => l !== ratio));
  };
  
  const toggleDropdown = (dropdown: 'color' | 'width' | 'opacity' | 'options' | 'levels') => {
    setActiveDropdown((prev) => (prev === dropdown ? null : dropdown));
  };

  return (
    <div
      style={{
        position: 'absolute',
        left: `${position.left}px`,
        top: `${position.top}px`,
        display: 'flex',
        alignItems: 'center',
        gap: '6px',
        padding: '6px 10px',
        borderRadius: '8px',
        background: 'rgba(14, 20, 32, 0.95)',
        border: '1px solid var(--border-glow)',
        boxShadow: '0 8px 32px 0 rgba(0, 0, 0, 0.6)',
        backdropFilter: 'blur(16px)',
        WebkitBackdropFilter: 'blur(16px)',
        zIndex: 1000001,
        userSelect: 'none',
        pointerEvents: 'auto',
      }}
    >
      {/* Color Trigger & Dropdown */}
      <div style={{ position: 'relative' }}>
        <button
          onClick={() => toggleDropdown('color')}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            background: activeDropdown === 'color' ? 'rgba(255,255,255,0.1)' : 'transparent',
            border: '1px solid rgba(255,255,255,0.1)',
            borderRadius: '6px',
            padding: '4px 8px',
            color: '#fff',
            fontSize: '11px',
            cursor: 'pointer',
            height: '26px',
            transition: 'all 0.15s ease',
          }}
        >
          <span
            style={{
              width: '12px',
              height: '12px',
              borderRadius: '50%',
              backgroundColor: selectedDrawing.color,
              border: '1px solid rgba(255,255,255,0.3)',
            }}
          />
          <span>Color</span>
          <ChevronDown size={12} style={{ opacity: 0.6 }} />
        </button>
        
        {activeDropdown === 'color' && (
          <div
            style={{
              ...dropdownPanelStyle(dropdownDirection),
              padding: '10px',
              display: 'grid',
              gridTemplateColumns: 'repeat(5, 1fr)',
              gap: '8px',
            }}
          >
            {colors.map((c) => (
               <div
                 key={c}
                 onClick={() => {
                   onUpdateColor(c);
                   setActiveDropdown(null);
                 }}
                 style={{
                   width: '20px',
                   height: '20px',
                   borderRadius: '50%',
                   backgroundColor: c,
                   cursor: 'pointer',
                   border: selectedDrawing.color === c ? '2px solid #fff' : '1px solid rgba(255,255,255,0.2)',
                   boxShadow: selectedDrawing.color === c ? '0 0 6px rgba(255,255,255,0.8)' : 'none',
                   transition: 'transform 0.1s ease',
                 }}
                 onMouseEnter={(e) => e.currentTarget.style.transform = 'scale(1.15)'}
                 onMouseLeave={(e) => e.currentTarget.style.transform = 'scale(1.0)'}
               />
            ))}
          </div>
        )}
      </div>

      {/* Line Width Trigger & Dropdown */}
      <div style={{ position: 'relative' }}>
        <button
          onClick={() => toggleDropdown('width')}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            background: activeDropdown === 'width' ? 'rgba(255,255,255,0.1)' : 'transparent',
            border: '1px solid rgba(255,255,255,0.1)',
            borderRadius: '6px',
            padding: '4px 8px',
            color: '#fff',
            fontSize: '11px',
            cursor: 'pointer',
            height: '26px',
            transition: 'all 0.15s ease',
          }}
        >
          <span>{selectedDrawing.lineWidth}px</span>
          <ChevronDown size={12} style={{ opacity: 0.6 }} />
        </button>

        {activeDropdown === 'width' && (
          <div
            style={{
              ...dropdownPanelStyle(dropdownDirection),
              padding: '6px',
              display: 'flex',
              flexDirection: 'column',
              gap: '4px',
              width: '80px',
            }}
          >
            {[1, 2, 3, 4].map((w) => {
              const isActive = selectedDrawing.lineWidth === w;
              return (
                <button
                  key={w}
                  onClick={() => {
                    onUpdateLineWidth(w);
                    setActiveDropdown(null);
                  }}
                  style={{
                    background: isActive ? 'var(--neon-cyan-glow)' : 'transparent',
                    border: 'none',
                    color: isActive ? 'var(--neon-cyan)' : 'var(--text-secondary)',
                    borderRadius: '4px',
                    padding: '6px 8px',
                    fontSize: '11px',
                    cursor: 'pointer',
                    textAlign: 'left',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    width: '100%',
                    fontWeight: isActive ? 600 : 400,
                    transition: 'all 0.1s ease',
                  }}
                  onMouseEnter={(e) => {
                    if (!isActive) e.currentTarget.style.background = 'rgba(255,255,255,0.05)';
                  }}
                  onMouseLeave={(e) => {
                    if (!isActive) e.currentTarget.style.background = 'transparent';
                  }}
                >
                  <span>{w}px</span>
                  <div style={{
                    width: '30px',
                    height: `${w}px`,
                    backgroundColor: selectedDrawing.color,
                    opacity: 0.8,
                  }} />
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Opacity Trigger & Dropdown */}
      <div style={{ position: 'relative' }}>
        <button
          onClick={() => toggleDropdown('opacity')}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            background: activeDropdown === 'opacity' ? 'rgba(255,255,255,0.1)' : 'transparent',
            border: '1px solid rgba(255,255,255,0.1)',
            borderRadius: '6px',
            padding: '4px 8px',
            color: '#fff',
            fontSize: '11px',
            cursor: 'pointer',
            height: '26px',
            transition: 'all 0.15s ease',
          }}
        >
          <span>Opacity: {Math.round(selectedDrawing.opacity * 100)}%</span>
          <ChevronDown size={12} style={{ opacity: 0.6 }} />
        </button>

        {activeDropdown === 'opacity' && (
          <div
            style={{
              ...dropdownPanelStyle(dropdownDirection),
              padding: '10px 12px',
              display: 'flex',
              flexDirection: 'column',
              gap: '8px',
              width: '120px',
            }}
          >
            <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>Opacity: {Math.round(selectedDrawing.opacity * 100)}%</div>
            <input
              type="range"
              min="0.1"
              max="1.0"
              step="0.05"
              value={selectedDrawing.opacity}
              onChange={(e) => onUpdateOpacity(parseFloat(e.target.value))}
              style={{
                width: '100%',
                accentColor: 'var(--neon-cyan)',
                cursor: 'pointer',
                height: '4px',
              }}
            />
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '4px', marginTop: '4px' }}>
              {[0.2, 0.5, 0.8, 1.0].map((v) => (
                <button
                  key={v}
                  onClick={() => onUpdateOpacity(v)}
                  style={{
                    background: 'rgba(255,255,255,0.05)',
                    border: '1px solid rgba(255,255,255,0.1)',
                    borderRadius: '4px',
                    color: '#fff',
                    fontSize: '9px',
                    padding: '2px',
                    cursor: 'pointer',
                  }}
                >
                  {Math.round(v * 100)}%
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Options / Group selection (Style Settings) Trigger & Dropdown */}
      {(selectedDrawing.type === 'box' || selectedDrawing.type === 'fibonacci') && (
        <div style={{ position: 'relative' }}>
          <button
            onClick={() => toggleDropdown('options')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              background: activeDropdown === 'options' ? 'rgba(255,255,255,0.1)' : 'transparent',
              border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: '6px',
              padding: '4px 8px',
              color: '#fff',
              fontSize: '11px',
              cursor: 'pointer',
              height: '26px',
              transition: 'all 0.15s ease',
            }}
          >
            <span>Style</span>
            <ChevronDown size={12} style={{ opacity: 0.6 }} />
          </button>

          {activeDropdown === 'options' && (
            <div
              style={{
                ...dropdownPanelStyle(dropdownDirection),
                padding: '10px 12px',
                display: 'flex',
                flexDirection: 'column',
                gap: '8px',
                width: '120px',
              }}
            >
              {/* Shading Toggle */}
              <label
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  fontSize: '11px',
                  color: 'var(--text-secondary)',
                  cursor: 'pointer',
                }}
              >
                <input
                  type="checkbox"
                  checked={selectedDrawing.fill}
                  onChange={(e) => onUpdateFill(e.target.checked)}
                  style={{
                    cursor: 'pointer',
                    accentColor: 'var(--neon-cyan)',
                  }}
                />
                Shading
              </label>

              {/* Extend Right Toggle */}
              {selectedDrawing.type === 'fibonacci' && onUpdateExtendRight && (
                <label
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    fontSize: '11px',
                    color: 'var(--text-secondary)',
                    cursor: 'pointer',
                  }}
                >
                  <input
                    type="checkbox"
                    checked={!!selectedDrawing.extendRight}
                    onChange={(e) => onUpdateExtendRight(e.target.checked)}
                    style={{
                      cursor: 'pointer',
                      accentColor: 'var(--neon-cyan)',
                    }}
                  />
                  Extend Right
                </label>
              )}
            </div>
          )}
        </div>
      )}

      {/* Fibonacci specific: Dynamic ratios levels editor */}
      {selectedDrawing.type === 'fibonacci' && onUpdateFibLevels && (
        <div style={{ position: 'relative' }}>
          <button
            onClick={() => toggleDropdown('levels')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              background: activeDropdown === 'levels' ? 'rgba(255,255,255,0.1)' : 'transparent',
              border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: '6px',
              padding: '4px 8px',
              color: '#fff',
              fontSize: '11px',
              cursor: 'pointer',
              height: '26px',
              transition: 'all 0.15s ease',
            }}
          >
            <span>Levels ({currentLevels.length})</span>
            <ChevronDown size={12} style={{ opacity: 0.6 }} />
          </button>

          {activeDropdown === 'levels' && (
            <div
              style={{
                ...dropdownPanelStyle(dropdownDirection),
                padding: '10px 12px',
                display: 'flex',
                flexDirection: 'column',
                gap: '8px',
                width: '180px',
              }}
            >
              <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-primary)' }}>Ratios Levels</span>
              
              {/* Add Custom Ratio */}
              <div style={{ display: 'flex', gap: '4px' }}>
                <input
                  type="text"
                  value={newLevelInput}
                  placeholder="e.g. 1.618"
                  onChange={(e) => setNewLevelInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      handleAddLevel();
                    }
                  }}
                  style={{
                    flex: 1,
                    background: 'rgba(255,255,255,0.05)',
                    border: '1px solid rgba(255,255,255,0.15)',
                    borderRadius: '4px',
                    color: '#fff',
                    fontSize: '10px',
                    padding: '3px 6px',
                    outline: 'none',
                  }}
                />
                <button
                  onClick={handleAddLevel}
                  style={{
                    background: 'var(--neon-cyan-glow)',
                    border: '1px solid var(--neon-cyan)',
                    color: 'var(--neon-cyan)',
                    borderRadius: '4px',
                    padding: '2px 6px',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <Plus size={10} />
                </button>
              </div>

              {/* Active Levels List */}
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '4px',
                  maxHeight: '130px',
                  overflowY: 'auto',
                  paddingRight: '2px',
                }}
              >
                {currentLevels.map((ratio) => (
                  <div
                    key={ratio}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '2px 6px',
                      borderRadius: '4px',
                      background: 'rgba(255,255,255,0.03)',
                      border: '1px solid rgba(255,255,255,0.05)',
                    }}
                  >
                    <span style={{ fontSize: '10px', color: '#fff', fontFamily: 'monospace' }}>
                      {ratio}
                    </span>
                    <button
                      onClick={() => handleRemoveLevel(ratio)}
                      disabled={currentLevels.length <= 1}
                      style={{
                        background: 'transparent',
                        border: 'none',
                        color: 'var(--text-muted)',
                        cursor: currentLevels.length <= 1 ? 'not-allowed' : 'pointer',
                        padding: '2px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        opacity: currentLevels.length <= 1 ? 0.3 : 1,
                      }}
                      onMouseEnter={(e) => {
                        if (currentLevels.length > 1) e.currentTarget.style.color = 'var(--neon-red)';
                      }}
                      onMouseLeave={(e) => {
                        if (currentLevels.length > 1) e.currentTarget.style.color = 'var(--text-muted)';
                      }}
                    >
                      <X size={10} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      <div style={{ width: '1px', height: '18px', background: 'rgba(255,255,255,0.15)' }} />

      {/* Delete Button */}
      <button
        onClick={onDelete}
        title="Delete Drawing"
        style={{
          background: 'transparent',
          border: 'none',
          color: 'var(--text-muted)',
          cursor: 'pointer',
          padding: '6px',
          borderRadius: '6px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          transition: 'all 0.15s ease',
          height: '26px',
          width: '26px',
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
        <Trash2 size={14} />
      </button>
    </div>
  );
}
