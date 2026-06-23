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

interface TradingTerminalProps {
  sidebarHidden: boolean;
}

export function TradingTerminal({ sidebarHidden }: TradingTerminalProps) {
  const [instrument, setInstrument] = useState('EURUSD');
  const [timeframe, setTimeframe] = useState('1h');
  const connected = useSignalsStore((state) => state.wsConnected);
  usePortfolio();

  const [rightHidden, setRightHidden] = useState(() => {
    return localStorage.getItem('terminal_right_hidden') === 'true';
  });
  const [leftWidth, setLeftWidth] = useState(72);
  const [chartHeight, setChartHeight] = useState(50);
  const [indicatorHeight, setIndicatorHeight] = useState(25);
  const [portfolioWidth, setPortfolioWidth] = useState(50);

  const handleToggleRightPanel = () => {
    setRightHidden((prev) => {
      const next = !prev;
      localStorage.setItem('terminal_right_hidden', String(next));
      return next;
    });
  };

  const handleLeftRightDrag = (e: React.MouseEvent) => {
    e.preventDefault();
    const startX = e.clientX;
    const startWidth = leftWidth;
    const container = e.currentTarget.parentElement;
    if (!container) return;
    const containerWidth = container.getBoundingClientRect().width;

    const onMouseMove = (moveEvent: MouseEvent) => {
      const deltaX = moveEvent.clientX - startX;
      const deltaPercent = (deltaX / containerWidth) * 100;
      setLeftWidth(Math.max(20, Math.min(85, startWidth + deltaPercent)));
    };

    const onMouseUp = () => {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    };

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
  };

  const handleVerticalDrag1 = (e: React.MouseEvent) => {
    e.preventDefault();
    const startY = e.clientY;
    const startChartHeight = chartHeight;
    const container = e.currentTarget.parentElement;
    if (!container) return;
    const containerHeight = container.getBoundingClientRect().height;

    const onMouseMove = (moveEvent: MouseEvent) => {
      const deltaY = moveEvent.clientY - startY;
      const deltaPercent = (deltaY / containerHeight) * 100;
      const nextChartHeight = Math.max(20, Math.min(80, startChartHeight + deltaPercent));
      if (nextChartHeight + indicatorHeight <= 90) {
        setChartHeight(nextChartHeight);
      }
    };

    const onMouseUp = () => {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    };

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
  };

  const handleVerticalDrag2 = (e: React.MouseEvent) => {
    e.preventDefault();
    const startY = e.clientY;
    const startIndicatorHeight = indicatorHeight;
    const container = e.currentTarget.parentElement;
    if (!container) return;
    const containerHeight = container.getBoundingClientRect().height;

    const onMouseMove = (moveEvent: MouseEvent) => {
      const deltaY = moveEvent.clientY - startY;
      const deltaPercent = (deltaY / containerHeight) * 100;
      const nextIndicatorHeight = Math.max(10, Math.min(50, startIndicatorHeight + deltaPercent));
      if (chartHeight + nextIndicatorHeight <= 90) {
        setIndicatorHeight(nextIndicatorHeight);
      }
    };

    const onMouseUp = () => {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    };

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
  };

  const handlePortfolioResize = (e: React.MouseEvent) => {
    e.preventDefault();
    const startX = e.clientX;
    const startPortfolioWidth = portfolioWidth;
    const container = e.currentTarget.parentElement;
    if (!container) return;
    const containerWidth = container.getBoundingClientRect().width;

    const onMouseMove = (moveEvent: MouseEvent) => {
      const deltaX = moveEvent.clientX - startX;
      const deltaPercent = (deltaX / containerWidth) * 100;
      setPortfolioWidth(Math.max(15, Math.min(85, startPortfolioWidth + deltaPercent)));
    };

    const onMouseUp = () => {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    };

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
  };

  return (
    <div style={{ display: 'grid', gridTemplateRows: '56px 1fr', height: '100%', overflow: 'hidden' }}>
      <Header
        instrument={instrument}
        setInstrument={setInstrument}
        timeframe={timeframe}
        setTimeframe={setTimeframe}
        wsConnected={connected}
        sidebarHidden={sidebarHidden}
        rightPanelHidden={rightHidden}
        onToggleRightPanel={handleToggleRightPanel}
      />

      <div style={{ display: 'flex', padding: 12, overflow: 'hidden', height: 'calc(100vh - 56px - 24px)', boxSizing: 'border-box', width: '100%', gap: 0 }}>
        {/* Left column */}
        <div style={{
          width: rightHidden ? '100%' : `${leftWidth}%`,
          flexShrink: 0,
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden'
        }}>
          {/* Chart (Row 1) */}
          <div className="glass-panel" style={{ height: `${chartHeight}%`, flexShrink: 0, display: 'flex', flexDirection: 'column', padding: 12, overflow: 'hidden', boxSizing: 'border-box' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8, paddingBottom: 8, borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
              <span style={{ fontWeight: 600, fontSize: 13 }}>{instrument} · {timeframe}</span>
              <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Real-time chart</span>
            </div>
            <div style={{ flex: 1, overflow: 'hidden' }}><CandleChart instrument={instrument} timeframe={timeframe} /></div>
          </div>

          {/* Divider 1 */}
          <div className="resize-handle-v" onMouseDown={handleVerticalDrag1} />

          {/* Indicator Panel (Row 2) */}
          <div style={{ height: `${indicatorHeight}%`, flexShrink: 0, overflow: 'hidden' }}>
            <IndicatorPanel />
          </div>

          {/* Divider 2 */}
          <div className="resize-handle-v" onMouseDown={handleVerticalDrag2} />

          {/* Bottom row (Row 3) - Portfolio & SignalLog */}
          <div style={{ flex: 1, minHeight: 0, display: 'flex', overflow: 'hidden', width: '100%', gap: 0 }}>
            <div style={{ width: `${portfolioWidth}%`, flexShrink: 0, height: '100%', overflow: 'hidden' }}>
              <Portfolio />
            </div>

            <div className="resize-handle-h" onMouseDown={handlePortfolioResize} />

            <div style={{ flex: 1, minWidth: 0, height: '100%', overflow: 'hidden' }}>
              <SignalLog />
            </div>
          </div>
        </div>

        {/* Vertical Separator left-right */}
        {!rightHidden && (
          <div className="resize-handle-h" onMouseDown={handleLeftRightDrag} />
        )}

        {/* Right column */}
        {!rightHidden && (
          <div style={{
            flex: 1,
            minWidth: 0,
            height: '100%',
            display: 'flex',
            flexDirection: 'column',
            gap: 12,
            overflow: 'hidden'
          }}>
            <FusionPanel instrument={instrument} />
            <NewsFeed />
            <ConfigEditor instrument={instrument} />
          </div>
        )}
      </div>
    </div>
  );
}
