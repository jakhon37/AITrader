import { Activity, AlertCircle, ArrowRight } from 'lucide-react';

interface ReplayConfigProps {
  instrument: string;
  setInstrument: (val: string) => void;
  timeframe: string;
  setTimeframe: (val: string) => void;
  startDate: string;
  setStartDate: (val: string) => void;
  initialCapital: number;
  setInitialCapital: (val: number) => void;
  mode: 'watch' | 'manual';
  setMode: (val: 'watch' | 'manual') => void;
  speed: number;
  setSpeed: (val: number) => void;
  calculateIndicators: boolean;
  setCalculateIndicators: (val: boolean) => void;
  handleStart: () => void;
  errorMsg: string | null;
}

export function ReplayConfig({
  instrument,
  setInstrument,
  timeframe,
  setTimeframe,
  startDate,
  setStartDate,
  initialCapital,
  setInitialCapital,
  mode,
  setMode,
  speed,
  setSpeed,
  calculateIndicators,
  setCalculateIndicators,
  handleStart,
  errorMsg,
}: ReplayConfigProps) {
  return (
    <div style={{ padding: 24, maxWidth: 650, margin: '40px auto', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 10 }}>
        <div style={{ display: 'flex', padding: 10, background: 'var(--neon-cyan-glow)', borderRadius: 8, color: 'var(--neon-cyan)' }}>
          <Activity size={28} />
        </div>
        <div>
          <h2 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', margin: 0 }}>Replay Studio</h2>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: 0 }}>Train your trading discipline or analyze indicators bar-by-bar.</p>
        </div>
      </div>

      {errorMsg && (
        <div style={{ padding: 12, background: 'rgba(255, 23, 68, 0.1)', border: '1px solid var(--neon-red)', borderRadius: 8, color: '#ff5252', display: 'flex', alignItems: 'center', gap: 10, fontSize: 13 }}>
          <AlertCircle size={18} />
          <span>{errorMsg}</span>
        </div>
      )}

      <div className="glass-panel" style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 18 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          {/* Instrument Selection */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)' }}>INSTRUMENT</label>
            <select 
              value={instrument} 
              onChange={(e) => setInstrument(e.target.value)}
              style={{ background: '#111827', border: '1px solid var(--border-glow)', padding: 10, borderRadius: 6, color: '#fff', fontSize: 14 }}
            >
              <option value="EURUSD">EURUSD (Euro / US Dollar)</option>
              <option value="GBPUSD">GBPUSD (Great British Pound / US Dollar)</option>
              <option value="USDJPY">USDJPY (US Dollar / Japanese Yen)</option>
              <option value="XAUUSD">XAUUSD (Gold Spot)</option>
            </select>
          </div>

          {/* Initial Capital */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)' }}>INITIAL BALANCE (USD)</label>
            <input 
              type="number" 
              value={initialCapital} 
              onChange={(e) => setInitialCapital(Number(e.target.value))}
              style={{ background: '#111827', border: '1px solid var(--border-glow)', padding: 10, borderRadius: 6, color: '#fff', fontSize: 14 }}
            />
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          {/* Start Date */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)' }}>START DATE</label>
            <input 
              type="date" 
              value={startDate} 
              onChange={(e) => setStartDate(e.target.value)}
              style={{ background: '#111827', border: '1px solid var(--border-glow)', padding: 10, borderRadius: 6, color: '#fff', fontSize: 14 }}
            />
          </div>

          {/* Timeframe */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)' }}>TIMEFRAME</label>
            <select 
              value={timeframe} 
              onChange={(e) => setTimeframe(e.target.value)}
              style={{ background: '#111827', border: '1px solid var(--border-glow)', padding: 10, borderRadius: 6, color: '#fff', fontSize: 14 }}
            >
              <option value="1m">1m</option>
              <option value="5m">5m</option>
              <option value="15m">15m</option>
              <option value="30m">30m</option>
              <option value="1h">1h</option>
              <option value="4h">4h</option>
              <option value="1d">1d</option>
            </select>
          </div>
        </div>

        {/* Mode Selector */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)' }}>REPLAY MODE</label>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <button 
              type="button"
              onClick={() => setMode('manual')}
              style={{ 
                padding: '12px 8px', 
                borderRadius: 8, 
                background: mode === 'manual' ? 'var(--neon-cyan-glow)' : 'transparent',
                border: `1px solid ${mode === 'manual' ? 'var(--neon-cyan)' : 'var(--border-glow)'}`,
                color: mode === 'manual' ? '#fff' : 'var(--text-secondary)',
                cursor: 'pointer',
                textAlign: 'left',
                display: 'flex',
                flexDirection: 'column',
                gap: 4
              }}
            >
              <span style={{ fontWeight: 600, fontSize: 14 }}>Trader Training Mode</span>
              <span style={{ fontSize: 11, opacity: 0.8 }}>Manually execute orders. Clock advances only when you press step.</span>
            </button>

            <button 
              type="button"
              onClick={() => setMode('watch')}
              style={{ 
                padding: '12px 8px', 
                borderRadius: 8, 
                background: mode === 'watch' ? 'var(--neon-cyan-glow)' : 'transparent',
                border: `1px solid ${mode === 'watch' ? 'var(--neon-cyan)' : 'var(--border-glow)'}`,
                color: mode === 'watch' ? '#fff' : 'var(--text-secondary)',
                cursor: 'pointer',
                textAlign: 'left',
                display: 'flex',
                flexDirection: 'column',
                gap: 4
              }}
            >
              <span style={{ fontWeight: 600, fontSize: 14 }}>Strategy Watch Mode</span>
              <span style={{ fontSize: 11, opacity: 0.8 }}>Watch indicators & model outputs compute automatically at selected speed.</span>
            </button>
          </div>
        </div>

        {/* Speed Selector (Only visible for Watch Mode) */}
        {mode === 'watch' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)' }}>SPEED MULTIPLIER ({speed}x)</label>
            <div style={{ display: 'flex', gap: 8 }}>
              {[1, 5, 10, 25, 50, 100].map((s) => (
                <button 
                  key={s} 
                  type="button"
                  onClick={() => setSpeed(s)}
                  style={{ 
                    flex: 1, 
                    padding: 8, 
                    borderRadius: 6, 
                    background: speed === s ? '#1f2937' : '#111827', 
                    border: `1px solid ${speed === s ? 'var(--neon-cyan)' : 'var(--border-glow)'}`,
                    color: speed === s ? '#fff' : 'var(--text-secondary)',
                    cursor: 'pointer' 
                  }}
                >
                  {s}x
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Indicator Calculations Switch */}
        <div style={{ 
          display: 'flex', 
          alignItems: 'center', 
          justifyContent: 'space-between', 
          padding: '12px 16px', 
          background: '#111827', 
          border: '1px solid var(--border-glow)', 
          borderRadius: 8, 
          marginTop: 4 
        }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2, maxWidth: '80%' }}>
            <span style={{ fontWeight: 600, fontSize: 13, color: '#fff' }}>Enable Technical Indicators</span>
            <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>Computes confluence and indicators (RSI, regime, etc.) on each bar. Turn off for maximum speed.</span>
          </div>
          <input 
            type="checkbox"
            checked={calculateIndicators}
            onChange={(e) => setCalculateIndicators(e.target.checked)}
            style={{ width: 18, height: 18, cursor: 'pointer', accentColor: 'var(--neon-cyan)' }}
          />
        </div>

        <button 
          type="button"
          onClick={handleStart}
          style={{ 
            marginTop: 10,
            padding: '14px', 
            borderRadius: 8, 
            background: 'linear-gradient(90deg, #00b4d8 0%, #0077b6 100%)',
            color: '#fff', 
            border: 'none', 
            fontWeight: 700, 
            fontSize: 15,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 8,
            boxShadow: '0 4px 14px rgba(0, 180, 216, 0.3)'
          }}
        >
          Start Replay Session
          <ArrowRight size={18} />
        </button>
      </div>
    </div>
  );
}
