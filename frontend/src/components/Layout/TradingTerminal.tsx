import { useState } from 'react';
import { Header } from './Header';
import { CandleChart } from '../Chart/CandleChart';
import { IndicatorPanel } from '../Chart/IndicatorPanel';
import { FusionPanel } from '../Panels/FusionPanel';
import { NewsFeed } from '../Panels/NewsFeed';
import { Portfolio } from '../Panels/Portfolio';
import { SignalLog } from '../Panels/SignalLog';
import { ConfigEditor } from '../Panels/ConfigEditor';
import { usePortfolio } from '../../hooks/usePortfolio';
import { useSignalsStore } from '../../store/signals';

export function TradingTerminal() {
  const [instrument, setInstrument] = useState('EURUSD');
  const [timeframe, setTimeframe] = useState('1h');
  const connected = useSignalsStore((state) => state.wsConnected);
  usePortfolio();

  return (
    <div style={{ display: 'grid', gridTemplateRows: '56px 1fr', height: '100%', overflow: 'hidden' }}>
      <Header instrument={instrument} setInstrument={setInstrument} timeframe={timeframe} setTimeframe={setTimeframe} wsConnected={connected} />

      <div style={{ display: 'grid', gridTemplateColumns: '3fr 1.15fr', gap: 12, padding: 12, overflow: 'hidden', height: 'calc(100vh - 56px - 24px)' }}>
        {/* Left column */}
        <div style={{ display: 'grid', gridTemplateRows: '3fr 1fr 1fr', gap: 12, overflow: 'hidden' }}>
          <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', padding: 12, overflow: 'hidden' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8, paddingBottom: 8, borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
              <span style={{ fontWeight: 600, fontSize: 13 }}>{instrument} · {timeframe}</span>
              <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Real-time chart</span>
            </div>
            <div style={{ flex: 1, overflow: 'hidden' }}><CandleChart instrument={instrument} timeframe={timeframe} /></div>
          </div>
          <div style={{ overflow: 'hidden' }}><IndicatorPanel /></div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, overflow: 'hidden' }}>
            <Portfolio />
            <SignalLog />
          </div>
        </div>

        {/* Right column */}
        <div style={{ display: 'grid', gridTemplateRows: 'auto 1fr auto', gap: 12, overflow: 'hidden' }}>
          <FusionPanel instrument={instrument} />
          <NewsFeed />
          <ConfigEditor instrument={instrument} />
        </div>
      </div>
    </div>
  );
}
