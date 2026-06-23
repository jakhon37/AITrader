import { useState, useEffect, useRef } from 'react';
import { 
  Play, 
  Pause, 
  Square, 
  ArrowRight, 
  TrendingUp, 
  TrendingDown, 
  Activity, 
  Award, 
  ShieldAlert, 
  BarChart2,
  AlertCircle
} from 'lucide-react';
import { 
  startReplay, 
  pauseReplay, 
  resumeReplay, 
  placeManualOrder, 
  closeManualPosition, 
  stopReplay, 
  getReplayState,
  changeReplayTimeframe,
  changeReplaySpeed
} from '../../api/client';
import { CandleChart } from '../Chart/CandleChart';

export function ReplayPage() {
  // Session Configuration State
  const [instrument, setInstrument] = useState('EURUSD');
  const [timeframe, setTimeframe] = useState('1h');
  const [startDate, setStartDate] = useState('2024-01-01');
  const [initialCapital, setInitialCapital] = useState(10000);
  const [mode, setMode] = useState<'watch' | 'manual'>('manual');
  const [speed, setSpeed] = useState(10);

  // Active Session State
  const [isActive, setIsActive] = useState(false);
  const [status, setStatus] = useState<'paused' | 'running' | 'ended'>('paused');
  const [currentTime, setCurrentTime] = useState<string | null>(null);
  const [sessionState, setSessionState] = useState<any>(null);
  const [scorecard, setScorecard] = useState<any>(null);

  // Manual Order Panel State
  const [orderSize, setOrderSize] = useState(1.0);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Auto Scroll Refs
  const tradeLogEndRef = useRef<HTMLDivElement>(null);

  // Check state on load
  useEffect(() => {
    getReplayState()
      .then((res) => {
        if (res.status === 'active') {
          setIsActive(true);
          setMode(res.session.mode);
          setStatus(res.session.status);
          setInstrument(res.session.instrument);
          if (res.session.timeframe) {
            setTimeframe(res.session.timeframe);
          }
          setSpeed(res.session.speed);
          setCurrentTime(res.session.current_time);
          setSessionState(res.session);
        }
      })
      .catch((err) => console.error('Failed to restore replay state:', err));
  }, []);

  // Listen for real-time WebSocket frames via custom event
  useEffect(() => {
    const handleReplayFrame = (e: Event) => {
      const customEvent = e as CustomEvent<any>;
      const { session_state } = customEvent.detail;
      if (session_state) {
        setSessionState(session_state);
        setStatus(session_state.status);
        setCurrentTime(session_state.current_time);
        if (session_state.timeframe) {
          setTimeframe(session_state.timeframe);
        }
        
        if (session_state.status === 'ended') {
          // Automatically fetch scorecard on completion
          handleStop();
        }
      }
    };
    window.addEventListener('replay_frame', handleReplayFrame);
    return () => window.removeEventListener('replay_frame', handleReplayFrame);
  }, []);

  // Auto-scroll trade log
  useEffect(() => {
    tradeLogEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [sessionState?.trade_history]);

  const handleStart = async () => {
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      const payload = {
        instrument,
        start_date: `${startDate}T00:00:00Z`,
        initial_capital: initialCapital,
        mode,
        speed: mode === 'watch' ? speed : 0.0,
        timeframe,
      };
      const res = await startReplay(payload);
      if (res.status === 'success') {
        setIsActive(true);
        setSessionState(res.session);
        setStatus(res.session.status);
        setCurrentTime(res.session.current_time);
        if (res.session.timeframe) {
          setTimeframe(res.session.timeframe);
        }
        setScorecard(null);
      }
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to start replay session.');
    }
  };

  const handlePause = async () => {
    try {
      const res = await pauseReplay();
      if (res.status === 'success') {
        setStatus('paused');
      }
    } catch (err) {
      console.error('Pause failed:', err);
    }
  };

  const handleResume = async () => {
    try {
      const res = await resumeReplay();
      if (res.status === 'success') {
        setStatus('running');
      }
    } catch (err) {
      console.error('Resume failed:', err);
    }
  };


  const handleStop = async () => {
    try {
      const res = await stopReplay();
      if (res.status === 'success') {
        setIsActive(false);
        setStatus('ended');
        if (res.report) {
          setScorecard(res.report);
        }
      }
    } catch (err) {
      console.error('Stop failed:', err);
    }
  };

  const handleTimeframeChange = async (newTf: string) => {
    try {
      const res = await changeReplayTimeframe(newTf);
      if (res.status === 'success') {
        setTimeframe(newTf);
        if (res.session) {
          setSessionState(res.session);
          setCurrentTime(res.session.current_time);
        }
      }
    } catch (err) {
      console.error('Failed to change timeframe:', err);
    }
  };

  const handleBuy = async () => {
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      const res = await placeManualOrder('buy', orderSize);
      if (res.status === 'success') {
        setSuccessMsg(`Market BUY ${orderSize} lots filled at ${res.order.filled_price}`);
      }
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to execute Buy order.');
    }
  };

  const handleSell = async () => {
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      const res = await placeManualOrder('sell', orderSize);
      if (res.status === 'success') {
        setSuccessMsg(`Market SELL ${orderSize} lots filled at ${res.order.filled_price}`);
      }
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to execute Sell order.');
    }
  };

  const handleClosePosition = async (inst: string) => {
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      const res = await closeManualPosition(inst);
      if (res.status === 'success') {
        setSuccessMsg(`Closed all positions for ${inst} at ${res.order.filled_price}`);
      }
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to close positions.');
    }
  };

  const formatDateTime = (isoString: string | null) => {
    if (!isoString) return '--';
    const dt = new Date(isoString);
    return dt.toUTCString().replace('GMT', 'UTC');
  };

  const formatCurrency = (val: number | undefined) => {
    if (val === undefined) return '$0.00';
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(val);
  };

  // Render Setup Configuration View
  if (!isActive && !scorecard) {
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

  // Render Performance Scorecard Report View
  if (scorecard && !isActive) {
    const isWin = scorecard.net_profit >= 0;
    return (
      <div style={{ padding: 24, maxWidth: 750, margin: '30px auto', display: 'flex', flexDirection: 'column', gap: 20 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid rgba(255,255,255,0.08)', paddingBottom: 15 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <Award size={36} color="var(--neon-cyan)" />
            <div>
              <h2 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', margin: 0 }}>Performance Report Card</h2>
              <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: 0 }}>Manual Replay session completed for {instrument}.</p>
            </div>
          </div>
          <button 
            type="button"
            onClick={() => setScorecard(null)}
            style={{ 
              padding: '8px 16px', 
              background: '#111827', 
              border: '1px solid var(--border-glow)', 
              color: '#fff', 
              borderRadius: 6,
              cursor: 'pointer',
              fontSize: 13
            }}
          >
            Return to Studio
          </button>
        </div>

        {/* Scorecard grids */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
          <div className="glass-panel" style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 4 }}>
            <span style={{ fontSize: 11, color: 'var(--text-secondary)', fontWeight: 600 }}>FINAL EQUITY</span>
            <span style={{ fontSize: 22, fontWeight: 700 }}>{formatCurrency(scorecard.final_equity)}</span>
          </div>

          <div className="glass-panel" style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 4 }}>
            <span style={{ fontSize: 11, color: 'var(--text-secondary)', fontWeight: 600 }}>NET PROFIT</span>
            <span style={{ fontSize: 22, fontWeight: 700, color: isWin ? 'var(--neon-green)' : 'var(--neon-red)', display: 'flex', alignItems: 'center', gap: 4 }}>
              {isWin ? <TrendingUp size={20} /> : <TrendingDown size={20} />}
              {scorecard.net_profit >= 0 ? '+' : ''}{formatCurrency(scorecard.net_profit)} ({scorecard.net_profit_pct.toFixed(2)}%)
            </span>
          </div>

          <div className="glass-panel" style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 4 }}>
            <span style={{ fontSize: 11, color: 'var(--text-secondary)', fontWeight: 600 }}>DISCIPLINE SCORE</span>
            <span style={{ fontSize: 22, fontWeight: 700, color: scorecard.discipline_score >= 80 ? 'var(--neon-green)' : scorecard.discipline_score >= 50 ? 'var(--neon-orange)' : 'var(--neon-red)', display: 'flex', alignItems: 'center', gap: 6 }}>
              <ShieldAlert size={20} />
              {scorecard.discipline_score.toFixed(1)}%
            </span>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
          <div className="glass-panel" style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 4 }}>
            <span style={{ fontSize: 11, color: 'var(--text-secondary)', fontWeight: 600 }}>TOTAL TRADES</span>
            <span style={{ fontSize: 20, fontWeight: 700 }}>{scorecard.total_trades}</span>
          </div>

          <div className="glass-panel" style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 4 }}>
            <span style={{ fontSize: 11, color: 'var(--text-secondary)', fontWeight: 600 }}>WIN RATE</span>
            <span style={{ fontSize: 20, fontWeight: 700 }}>{scorecard.win_rate.toFixed(1)}%</span>
          </div>

          <div className="glass-panel" style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 4 }}>
            <span style={{ fontSize: 11, color: 'var(--text-secondary)', fontWeight: 600 }}>PROFIT FACTOR</span>
            <span style={{ fontSize: 20, fontWeight: 700 }}>{scorecard.profit_factor === Infinity ? '∞' : scorecard.profit_factor.toFixed(2)}</span>
          </div>
        </div>

        {/* Trade History details */}
        <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', height: 280 }}>
          <div style={{ padding: '12px 16px', borderBottom: '1px solid rgba(255,255,255,0.06)', fontWeight: 600, fontSize: 14 }}>
            Executed Trade Log
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: 8 }}>
            {scorecard.trades && scorecard.trades.length > 0 ? (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12, textAlign: 'left' }}>
                <thead>
                  <tr style={{ color: 'var(--text-secondary)', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                    <th style={{ padding: '8px 12px' }}>Direction</th>
                    <th style={{ padding: '8px 12px' }}>Size</th>
                    <th style={{ padding: '8px 12px' }}>Entry Price</th>
                    <th style={{ padding: '8px 12px' }}>Exit Price</th>
                    <th style={{ padding: '8px 12px' }}>P&L ($)</th>
                    <th style={{ padding: '8px 12px' }}>P&L (%)</th>
                  </tr>
                </thead>
                <tbody>
                  {scorecard.trades.map((t: any, idx: number) => {
                    const isTradeWin = t.pnl >= 0;
                    return (
                      <tr key={idx} style={{ borderBottom: '1px solid rgba(255,255,255,0.02)', verticalAlign: 'middle' }}>
                        <td style={{ padding: '8px 12px', fontWeight: 600, color: t.side === 'long' ? 'var(--neon-green)' : 'var(--neon-red)' }}>
                          {t.side.toUpperCase()}
                        </td>
                        <td style={{ padding: '8px 12px' }}>{t.size.toFixed(2)}</td>
                        <td style={{ padding: '8px 12px' }}>{t.entry_price.toFixed(5)}</td>
                        <td style={{ padding: '8px 12px' }}>{t.exit_price.toFixed(5)}</td>
                        <td style={{ padding: '8px 12px', color: isTradeWin ? 'var(--neon-green)' : 'var(--neon-red)', fontWeight: 600 }}>
                          {isTradeWin ? '+' : ''}{t.pnl.toFixed(2)}
                        </td>
                        <td style={{ padding: '8px 12px', color: isTradeWin ? 'var(--neon-green)' : 'var(--neon-red)' }}>
                          {isTradeWin ? '+' : ''}{(t.pnl_pct * 100).toFixed(2)}%
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            ) : (
              <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>No trades were placed during this session.</div>
            )}
          </div>
        </div>
      </div>
    );
  }

  // Active Session Layout View
  return (
    <div style={{ display: 'grid', gridTemplateRows: '56px 1fr', height: '100vh', overflow: 'hidden' }}>
      {/* Session Header Controls */}
      <header style={{ 
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'center', 
        padding: '0 20px', 
        background: 'rgba(7, 9, 14, 0.8)', 
        borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
        zIndex: 10
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <span style={{ fontSize: 16, fontWeight: 700, color: 'var(--neon-cyan)', display: 'flex', alignItems: 'center', gap: 6 }}>
            <Activity size={18} />
            REPLAY STUDIO
          </span>
          <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
            Instrument: <strong style={{ color: '#fff' }}>{instrument}</strong>
          </span>
          <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
            Timeframe: <strong style={{ color: '#fff' }}>{timeframe}</strong>
          </span>
          <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
            Mode: <strong style={{ color: '#fff' }}>{mode.toUpperCase()}</strong>
          </span>
          <span style={{ fontSize: 12, background: 'rgba(255,255,255,0.06)', padding: '3px 8px', borderRadius: 4, color: 'var(--text-secondary)' }}>
            Virtual Clock: <strong style={{ color: 'var(--neon-cyan)', fontFamily: 'monospace' }}>{formatDateTime(currentTime)}</strong>
          </span>
        </div>

        {/* Buttons Control Header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {status === 'running' ? (
            <button 
              onClick={handlePause}
              style={{ display: 'flex', alignItems: 'center', gap: 6, background: '#1e2937', border: '1px solid var(--border-glow)', padding: '6px 12px', borderRadius: 6, cursor: 'pointer', color: '#fff', fontSize: 13 }}
            >
              <Pause size={14} />
              Pause
            </button>
          ) : (
            <button 
              onClick={handleResume}
              style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'var(--neon-cyan-glow)', border: '1px solid var(--neon-cyan)', padding: '6px 12px', borderRadius: 6, cursor: 'pointer', color: '#fff', fontSize: 13 }}
            >
              <Play size={14} />
              Play
            </button>
          )}

          {/* Dynamic Speed Selector */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, background: '#111827', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 6, padding: '5px 10px' }}>
            <span style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 600 }}>SPEED:</span>
            <select
              value={speed}
              onChange={async (e) => {
                const newSpeed = Number(e.target.value);
                setSpeed(newSpeed);
                try {
                  await changeReplaySpeed(newSpeed);
                } catch (err) {
                  console.error('Failed to change speed:', err);
                }
              }}
              style={{
                background: 'transparent',
                border: 'none',
                color: '#fff',
                fontSize: 12,
                cursor: 'pointer',
                outline: 'none',
              }}
            >
              {[1, 3, 5, 10, 20, 50, 100].map((s) => (
                <option key={s} value={s}>{s}x</option>
              ))}
            </select>
          </div>

          {/* Status Badge */}
          <span style={{ 
            fontSize: 9, 
            fontWeight: 700, 
            textTransform: 'uppercase', 
            color: status === 'running' ? 'var(--neon-green)' : status === 'paused' ? 'var(--neon-cyan)' : '#ff5252',
            background: status === 'running' ? 'rgba(0,230,118,0.1)' : status === 'paused' ? 'rgba(0,229,255,0.1)' : 'rgba(255,23,68,0.1)',
            padding: '4px 8px',
            borderRadius: 4,
            letterSpacing: '0.05em'
          }}>
            {status}
          </span>

          <button 
            onClick={handleStop}
            style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(255, 23, 68, 0.1)', border: '1px solid var(--neon-red)', padding: '6px 12px', borderRadius: 6, cursor: 'pointer', color: '#ff5252', fontSize: 13 }}
          >
            <Square size={12} fill="#ff5252" />
            End Session
          </button>
        </div>
      </header>

      {/* Main Studio Split Layout */}
      <div style={{ 
        display: 'grid', 
        gridTemplateColumns: '3fr 1.25fr', 
        gap: 12, 
        padding: 12, 
        overflow: 'hidden', 
        height: 'calc(100vh - 56px)' 
      }}>
        {/* Left Side: Chart Section */}
        <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', padding: 12, overflow: 'hidden' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8, paddingBottom: 8, borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
              <span style={{ fontWeight: 700, fontSize: 14, color: '#fff' }}>{instrument}</span>
              <div style={{ display: 'flex', background: '#111827', borderRadius: 6, padding: 2, border: '1px solid var(--border-glow)' }}>
                {['1m', '5m', '15m', '30m', '1h', '4h', '1d'].map((tf) => (
                  <button
                    key={tf}
                    onClick={() => handleTimeframeChange(tf)}
                    style={{
                      background: timeframe === tf ? 'var(--neon-cyan-glow)' : 'transparent',
                      border: 'none',
                      color: timeframe === tf ? '#fff' : 'var(--text-secondary)',
                      padding: '4px 10px',
                      borderRadius: 4,
                      fontSize: 12,
                      fontWeight: 600,
                      cursor: 'pointer',
                      transition: 'all 0.2s ease',
                    }}
                  >
                    {tf}
                  </button>
                ))}
              </div>
            </div>



            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Historical Simulation</span>
          </div>
          <div style={{ flex: 1, overflow: 'hidden' }}>
            <CandleChart instrument={instrument} timeframe={timeframe} virtualEndTime={currentTime || undefined} />
          </div>
        </div>

        {/* Right Side: Operations, Position, Trade Log */}
        <div style={{ display: 'grid', gridTemplateRows: 'auto auto 1fr', gap: 12, overflow: 'hidden' }}>
          
          {/* 1. Order Entry Panel (Manual Mode Only) */}
          {mode === 'manual' ? (
            <div className="glass-panel" style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontWeight: 600, fontSize: 13, color: 'var(--text-primary)' }}>Order Ticket</span>
                <span style={{ fontSize: 10, background: 'rgba(255,255,255,0.04)', padding: '2px 6px', borderRadius: 3 }}>Market Execution</span>
              </div>

              {errorMsg && (
                <div style={{ fontSize: 11, color: 'var(--neon-red)', background: 'rgba(255,23,68,0.05)', padding: 6, borderRadius: 4 }}>
                  {errorMsg}
                </div>
              )}
              {successMsg && (
                <div style={{ fontSize: 11, color: 'var(--neon-green)', background: 'rgba(0,230,118,0.05)', padding: 6, borderRadius: 4 }}>
                  {successMsg}
                </div>
              )}

              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>LOT SIZE:</span>
                <input 
                  type="number" 
                  step="0.01" 
                  value={orderSize} 
                  onChange={(e) => setOrderSize(Math.max(0.01, Number(e.target.value)))}
                  style={{ flex: 1, background: '#111827', border: '1px solid var(--border-glow)', padding: '6px 10px', borderRadius: 4, color: '#fff', fontSize: 13 }}
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                <button 
                  onClick={handleBuy}
                  style={{ 
                    padding: '10px', 
                    borderRadius: 6, 
                    background: 'var(--neon-green)', 
                    color: '#000', 
                    border: 'none', 
                    fontWeight: 700, 
                    cursor: 'pointer',
                    fontSize: 13,
                    boxShadow: '0 0 10px var(--neon-green-glow)'
                  }}
                >
                  BUY
                </button>
                <button 
                  onClick={handleSell}
                  style={{ 
                    padding: '10px', 
                    borderRadius: 6, 
                    background: 'var(--neon-red)', 
                    color: '#fff', 
                    border: 'none', 
                    fontWeight: 700, 
                    cursor: 'pointer',
                    fontSize: 13,
                    boxShadow: '0 0 10px var(--neon-red-glow)'
                  }}
                >
                  SELL
                </button>
              </div>
            </div>
          ) : (
            <div className="glass-panel" style={{ padding: 14, textAlign: 'center', color: 'var(--text-secondary)', fontSize: 12 }}>
              Manual trades are disabled in Strategy Watch Mode.
            </div>
          )}

          {/* 2. Portfolio Stats */}
          <div className="glass-panel" style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 10 }}>
            <span style={{ fontWeight: 600, fontSize: 13 }}>Portfolio State</span>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              <div style={{ display: 'flex', flexDirection: 'column' }}>
                <span style={{ fontSize: 10, color: 'var(--text-secondary)' }}>BALANCE</span>
                <span style={{ fontSize: 15, fontWeight: 700 }}>
                  {formatCurrency(sessionState?.current_portfolio?.balance)}
                </span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column' }}>
                <span style={{ fontSize: 10, color: 'var(--text-secondary)' }}>EQUITY</span>
                <span style={{ fontSize: 15, fontWeight: 700 }}>
                  {formatCurrency(sessionState?.current_portfolio?.equity)}
                </span>
              </div>
            </div>

            {/* Position details */}
            <div style={{ marginTop: 5, borderTop: '1px solid rgba(255,255,255,0.04)', paddingTop: 8 }}>
              <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)' }}>OPEN POSITIONS</span>
              {sessionState?.open_positions && sessionState.open_positions.length > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 6 }}>
                  {sessionState.open_positions.map((pos: any, idx: number) => {
                    const isLong = pos.side.toLowerCase() === 'buy' || pos.side.toLowerCase() === 'long';
                    const isPnlWin = pos.unrealized_pnl >= 0;
                    return (
                      <div key={idx} style={{ 
                        display: 'flex', 
                        justifyContent: 'space-between', 
                        alignItems: 'center', 
                        background: 'rgba(255,255,255,0.02)', 
                        padding: 8, 
                        borderRadius: 6,
                        borderLeft: `3px solid ${isLong ? 'var(--neon-green)' : 'var(--neon-red)'}`
                      }}>
                        <div style={{ display: 'flex', flexDirection: 'column' }}>
                          <span style={{ fontSize: 12, fontWeight: 700 }}>
                            {pos.instrument} <span style={{ color: isLong ? 'var(--neon-green)' : 'var(--neon-red)', fontSize: 10 }}>{isLong ? 'LONG' : 'SHORT'}</span>
                          </span>
                          <span style={{ fontSize: 10, color: 'var(--text-secondary)' }}>
                            Size: {pos.size} · Entry: {pos.entry_price.toFixed(5)}
                          </span>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <span style={{ fontSize: 12, fontWeight: 700, color: isPnlWin ? 'var(--neon-green)' : 'var(--neon-red)' }}>
                            {isPnlWin ? '+' : ''}{pos.unrealized_pnl.toFixed(2)}
                          </span>
                          {mode === 'manual' && (
                            <button 
                              onClick={() => handleClosePosition(pos.instrument)}
                              style={{ padding: '3px 6px', background: 'var(--neon-orange-glow)', border: '1px solid var(--neon-orange)', color: 'var(--neon-orange)', borderRadius: 4, fontSize: 9, cursor: 'pointer' }}
                            >
                              CLOSE
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div style={{ fontSize: 11, color: 'var(--text-muted)', textAlign: 'center', padding: 12 }}>No open positions.</div>
              )}
            </div>
          </div>

          {/* 3. Replay Trade History log */}
          <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <div style={{ padding: '10px 14px', borderBottom: '1px solid rgba(255,255,255,0.06)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontWeight: 600, fontSize: 13, display: 'flex', alignItems: 'center', gap: 4 }}>
                <BarChart2 size={14} />
                Session Trade Log
              </span>
              <span style={{ fontSize: 10, color: 'var(--text-secondary)' }}>
                Count: {sessionState?.trade_history?.length || 0}
              </span>
            </div>

            <div style={{ flex: 1, overflowY: 'auto', padding: 8 }}>
              {sessionState?.trade_history && sessionState.trade_history.length > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {sessionState.trade_history.map((t: any, idx: number) => {
                    const isTradeWin = t.pnl >= 0;
                    return (
                      <div key={idx} style={{ 
                        display: 'flex', 
                        justifyContent: 'space-between', 
                        alignItems: 'center', 
                        background: 'rgba(255,255,255,0.01)', 
                        padding: '6px 8px', 
                        borderRadius: 4,
                        fontSize: 11
                      }}>
                        <div style={{ display: 'flex', flexDirection: 'column' }}>
                          <span style={{ fontWeight: 600, color: t.side === 'long' ? 'var(--neon-green)' : 'var(--neon-red)' }}>
                            {t.side.toUpperCase()} · {t.size} Lots
                          </span>
                          <span style={{ fontSize: 9, color: 'var(--text-secondary)' }}>
                            In: {t.entry_price.toFixed(5)} · Out: {t.exit_price.toFixed(5)}
                          </span>
                        </div>
                        <div style={{ textAlign: 'right' }}>
                          <span style={{ fontWeight: 700, color: isTradeWin ? 'var(--neon-green)' : 'var(--neon-red)' }}>
                            {isTradeWin ? '+' : ''}{t.pnl.toFixed(2)}
                          </span>
                          <div style={{ fontSize: 9, color: isTradeWin ? 'var(--neon-green)' : 'var(--neon-red)' }}>
                            {isTradeWin ? '+' : ''}{(t.pnl_pct * 100).toFixed(2)}%
                          </div>
                        </div>
                      </div>
                    );
                  })}
                  <div ref={tradeLogEndRef} />
                </div>
              ) : (
                <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)', fontSize: 12 }}>No completed trades.</div>
              )}
            </div>
          </div>
          
        </div>
      </div>
    </div>
  );
}
