import { useState, useEffect, useRef } from 'react';
import { 
  startReplay, 
  pauseReplay, 
  resumeReplay, 
  placeManualOrder, 
  closeManualPosition, 
  stopReplay, 
  getReplayState,
  changeReplayTimeframe,
  changeReplaySpeed,
  changeReplayIndicators
} from '../../api/client';
import { CandleChart } from '../Chart/CandleChart';
import { ReplayConfig } from './components/ReplayConfig';
import { PerformanceScorecard } from './components/PerformanceScorecard';
import { ActiveSessionHeader } from './components/ActiveSessionHeader';
import { OrderTicket } from './components/OrderTicket';
import { PortfolioState } from './components/PortfolioState';
import { SessionTradeLog } from './components/SessionTradeLog';

export function ReplayPage() {
  // Session Configuration State
  const [instrument, setInstrument] = useState('EURUSD');
  const [timeframe, setTimeframe] = useState('1h');
  const [startDate, setStartDate] = useState('2024-01-01');
  const [initialCapital, setInitialCapital] = useState(10000);
  const [mode, setMode] = useState<'watch' | 'manual'>('manual');
  const [speed, setSpeed] = useState(10);
  const [calculateIndicators, setCalculateIndicators] = useState(true);

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
          if (res.session.calculate_indicators !== undefined) {
            setCalculateIndicators(res.session.calculate_indicators);
          }
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
        if (session_state.calculate_indicators !== undefined) {
          setCalculateIndicators(session_state.calculate_indicators);
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
        calculate_indicators: calculateIndicators,
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

  const handleSpeedChange = async (newSpeed: number) => {
    setSpeed(newSpeed);
    try {
      await changeReplaySpeed(newSpeed);
    } catch (err) {
      console.error('Failed to change speed:', err);
    }
  };

  const handleIndicatorsChange = async (checked: boolean) => {
    setCalculateIndicators(checked);
    try {
      await changeReplayIndicators(checked);
    } catch (err) {
      console.error('Failed to change indicators status:', err);
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

  // 1. Setup Configuration View
  if (!isActive && !scorecard) {
    return (
      <ReplayConfig
        instrument={instrument}
        setInstrument={setInstrument}
        timeframe={timeframe}
        setTimeframe={setTimeframe}
        startDate={startDate}
        setStartDate={setStartDate}
        initialCapital={initialCapital}
        setInitialCapital={setInitialCapital}
        mode={mode}
        setMode={setMode}
        speed={speed}
        setSpeed={setSpeed}
        calculateIndicators={calculateIndicators}
        setCalculateIndicators={setCalculateIndicators}
        handleStart={handleStart}
        errorMsg={errorMsg}
      />
    );
  }

  // 2. Scorecard View
  if (scorecard && !isActive) {
    return (
      <PerformanceScorecard
        scorecard={scorecard}
        instrument={instrument}
        setScorecard={setScorecard}
        formatCurrency={formatCurrency}
      />
    );
  }

  // 3. Active Session View
  return (
    <div style={{ display: 'grid', gridTemplateRows: '56px 1fr', height: '100vh', overflow: 'hidden' }}>
      <ActiveSessionHeader
        instrument={instrument}
        timeframe={timeframe}
        mode={mode}
        currentTime={currentTime}
        formatDateTime={formatDateTime}
        status={status}
        handlePause={handlePause}
        handleResume={handleResume}
        speed={speed}
        onSpeedChange={handleSpeedChange}
        calculateIndicators={calculateIndicators}
        onIndicatorsChange={handleIndicatorsChange}
        handleStop={handleStop}
      />

      <div style={{ 
        display: 'grid', 
        gridTemplateColumns: '3fr 1.25fr', 
        gap: 12, 
        padding: 12, 
        overflow: 'hidden', 
        height: 'calc(100vh - 56px)' 
      }}>
        {/* Left: Chart */}
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

        {/* Right: Operations, Position, and Trade Log */}
        <div style={{ display: 'grid', gridTemplateRows: 'auto auto 1fr', gap: 12, overflow: 'hidden' }}>
          {mode === 'manual' ? (
            <OrderTicket
              orderSize={orderSize}
              setOrderSize={setOrderSize}
              handleBuy={handleBuy}
              handleSell={handleSell}
              errorMsg={errorMsg}
              successMsg={successMsg}
            />
          ) : (
            <div className="glass-panel" style={{ padding: 14, textAlign: 'center', color: 'var(--text-secondary)', fontSize: 12 }}>
              Manual trades are disabled in Strategy Watch Mode.
            </div>
          )}

          <PortfolioState
            sessionState={sessionState}
            formatCurrency={formatCurrency}
            mode={mode}
            handleClosePosition={handleClosePosition}
          />

          <SessionTradeLog
            sessionState={sessionState}
            tradeLogEndRef={tradeLogEndRef}
          />
        </div>
      </div>
    </div>
  );
}
