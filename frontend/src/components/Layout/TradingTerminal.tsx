import { useEffect, useState } from 'react';
import { Header } from './Header';
import { CandleChart } from '../Chart/CandleChart';
import { ChartTimezoneSelector } from '../Chart/ChartTimezoneSelector';
import { ChartViewportToggle } from '../Chart/ChartViewportToggle';
import { useChartTimezone } from '../../hooks/useChartTimezone';
import type { ChartViewportMode } from '../Chart/utils';
import { IndicatorPanel } from '../Chart/IndicatorPanel';
import { FusionPanel } from '../Panels/FusionPanel';
import { NewsFeed } from '../Panels/NewsFeed';
import { Portfolio } from '../Panels/Portfolio';
import { SignalLog } from '../Panels/SignalLog';
import { ConfigEditor } from '../Panels/ConfigEditor';
import {
  focusChartPair,
  getDataInstruments,
  getFundamentalSignals,
  getLatestSignals,
  getTradeSignals,
  releaseReplaySession,
} from '../../api/client';
import { useSignalsStore } from '../../store/signals';
import { useLiveChartStatus } from '../../hooks/useLiveChartStatus';
import { usePortfolio } from '../../hooks/usePortfolio';
import { LiveChartStatus } from './LiveChartStatus';
import { ChevronDown, ChevronUp, Briefcase } from 'lucide-react';

interface TradingTerminalProps {
  sidebarHidden: boolean;
}

export function TradingTerminal({ sidebarHidden }: TradingTerminalProps) {
  const [enabledInstruments, setEnabledInstruments] = useState<string[]>([]);
  const [instrument, setInstrument] = useState('EURUSD');
  const [timeframe, setTimeframe] = useState('1h');
  const [chartViewportMode, setChartViewportMode] = useState<ChartViewportMode>(() => {
    const saved = localStorage.getItem('terminal_chart_viewport');
    return saved === 'fit-all' ? 'fit-all' : 'auto';
  });
  const connected = useSignalsStore((state) => state.wsConnected);
  const initTradeSignals = useSignalsStore((state) => state.initTradeSignals);
  const initFundamentalSignals = useSignalsStore((state) => state.initFundamentalSignals);
  const setTechnicalSignal = useSignalsStore((state) => state.setTechnicalSignal);
  const addTradeSignal = useSignalsStore((state) => state.addTradeSignal);
  const { timezone, setTimezone, displayLabel } = useChartTimezone();
  const liveStatus = useLiveChartStatus(instrument, timeframe, connected);
  usePortfolio();

  useEffect(() => {
    releaseReplaySession().catch(() => {
      /* non-fatal: terminal still works if release fails */
    });
  }, []);

  useEffect(() => {
    focusChartPair(instrument, timeframe).catch(() => {
      /* chart still loads from store if focus call fails */
    });
  }, [instrument, timeframe]);

  useEffect(() => {
    getTradeSignals()
      .then((signals) => initTradeSignals(Array.isArray(signals) ? signals : []))
      .catch(() => {});
  }, [initTradeSignals]);

  useEffect(() => {
    getFundamentalSignals()
      .then((signals) => initFundamentalSignals(Array.isArray(signals) ? signals : []))
      .catch(() => {});
  }, [initFundamentalSignals]);

  useEffect(() => {
    getLatestSignals(instrument)
      .then((payload) => {
        if (payload?.technical) setTechnicalSignal(payload.technical);
        if (payload?.trade) addTradeSignal(payload.trade);
      })
      .catch(() => {});
  }, [instrument, setTechnicalSignal, addTradeSignal]);

  useEffect(() => {
    getDataInstruments()
      .then((data) => {
        const list = data.enabled?.length ? data.enabled : data.supported;
        setEnabledInstruments(list);
        if (list.length && !list.includes(instrument)) {
          setInstrument(list[0]);
        }
      })
      .catch(() => {
        /* Header falls back to default instrument list */
      });
  }, []);

  const [rightHidden, setRightHidden] = useState(() => {
    return localStorage.getItem('terminal_right_hidden') === 'true';
  });

  // Right column individual collapses
  const [fusionCollapsed, setFusionCollapsed] = useState(() => {
    return localStorage.getItem('terminal_fusion_collapsed') === 'true';
  });
  const [newsCollapsed, setNewsCollapsed] = useState(() => {
    return localStorage.getItem('terminal_news_collapsed') === 'true';
  });
  const [configCollapsed, setConfigCollapsed] = useState(() => {
    return localStorage.getItem('terminal_config_collapsed') === 'true';
  });

  // Left column downside collapses
  const [indicatorCollapsed, setIndicatorCollapsed] = useState(() => {
    return localStorage.getItem('terminal_indicator_collapsed') === 'true';
  });
  const [bottomCollapsed, setBottomCollapsed] = useState(() => {
    return localStorage.getItem('terminal_bottom_collapsed') === 'true';
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

  const handleToggleFusionCollapsed = () => {
    setFusionCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem('terminal_fusion_collapsed', String(next));
      return next;
    });
  };

  const handleToggleNewsCollapsed = () => {
    setNewsCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem('terminal_news_collapsed', String(next));
      return next;
    });
  };

  const handleToggleConfigCollapsed = () => {
    setConfigCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem('terminal_config_collapsed', String(next));
      return next;
    });
  };

  const handleToggleIndicatorCollapsed = () => {
    setIndicatorCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem('terminal_indicator_collapsed', String(next));
      return next;
    });
  };

  const handleToggleBottomCollapsed = () => {
    setBottomCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem('terminal_bottom_collapsed', String(next));
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
        instruments={enabledInstruments.length > 0 ? enabledInstruments : undefined}
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
          {/* Chart (Row 1) - Fills remaining space dynamically */}
          <div className="glass-panel" style={{ flex: 1, display: 'flex', flexDirection: 'column', padding: 12, overflow: 'hidden', boxSizing: 'border-box' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8, paddingBottom: 8, borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <span style={{ fontWeight: 600, fontSize: 13 }}>{instrument} · {timeframe}</span>
                <ChartViewportToggle
                  mode={chartViewportMode}
                  onChange={(mode) => {
                    setChartViewportMode(mode);
                    localStorage.setItem('terminal_chart_viewport', mode);
                  }}
                />
                <ChartTimezoneSelector timezone={timezone} onChange={setTimezone} />
              </div>
              <LiveChartStatus
                status={liveStatus}
                wsConnected={connected}
                displayTimezone={`Display ${displayLabel}`}
              />
            </div>
            <div style={{ flex: 1, overflow: 'hidden' }}>
              <CandleChart instrument={instrument} timeframe={timeframe} viewportMode={chartViewportMode} />
            </div>
          </div>

          {/* Divider 1 */}
          {!indicatorCollapsed && (
            <div className="resize-handle-v" onMouseDown={handleVerticalDrag1} />
          )}

          {/* Indicator Panel (Row 2) */}
          <div
            className={`glass-panel ${indicatorCollapsed ? '' : 'panel-shell'}`}
            style={{
              height: indicatorCollapsed ? '36px' : `${indicatorHeight}%`,
              flexShrink: 0,
              minHeight: indicatorCollapsed ? '36px' : 60,
              padding: 0,
              boxSizing: 'border-box',
              marginTop: 10,
            }}
          >
            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '8px 12px',
              borderBottom: indicatorCollapsed ? 'none' : '1px solid rgba(255,255,255,0.05)',
              height: 36,
              boxSizing: 'border-box',
              width: '100%'
            }}>
              <span style={{ fontWeight: 600, fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-secondary)' }}>Indicator Panels (RSI & MACD)</span>
              <button
                onClick={handleToggleIndicatorCollapsed}
                style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', padding: 0, display: 'flex', alignItems: 'center' }}
              >
                {indicatorCollapsed ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
              </button>
            </div>
            {!indicatorCollapsed && (
              <div className="panel-body" style={{ padding: 8 }}>
                <IndicatorPanel instrument={instrument} timeframe={timeframe} />
              </div>
            )}
          </div>

          {/* Divider 2 */}
          {!bottomCollapsed && (
            <div className="resize-handle-v" onMouseDown={handleVerticalDrag2} />
          )}

          {/* Bottom row (Row 3) - Portfolio & SignalLog */}
          <div
            className={bottomCollapsed ? 'glass-panel' : ''}
            style={{
              height: bottomCollapsed ? '36px' : '30%',
              minHeight: bottomCollapsed ? '36px' : 80,
              flexShrink: 0,
              display: 'flex',
              flexDirection: bottomCollapsed ? 'column' : 'row',
              overflow: 'hidden',
              width: '100%',
              gap: 0,
              marginTop: 10,
              boxSizing: 'border-box',
            }}
          >
            {bottomCollapsed ? (
              <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '8px 12px',
                height: 36,
                boxSizing: 'border-box',
                width: '100%'
              }}>
                <span style={{ fontWeight: 600, fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Briefcase size={13} color="var(--neon-cyan)" /> Operations (Portfolio & Signal Feed)
                </span>
                <button
                  onClick={handleToggleBottomCollapsed}
                  style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', padding: 0, display: 'flex', alignItems: 'center' }}
                >
                  <ChevronDown size={14} />
                </button>
              </div>
            ) : (
              <>
                <div style={{ width: `${portfolioWidth}%`, flexShrink: 0, height: '100%', minHeight: 0, overflow: 'hidden', position: 'relative', display: 'flex', flexDirection: 'column' }}>
                  {/* Header collapse button is added inside Portfolio.tsx or custom wrapper */}
                  <div style={{ position: 'absolute', top: 16, right: 16, zIndex: 10 }}>
                    <button
                      onClick={handleToggleBottomCollapsed}
                      title="Collapse Operations Panel"
                      style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', padding: 0 }}
                    >
                      <ChevronUp size={14} />
                    </button>
                  </div>
                  <Portfolio />
                </div>

                <div className="resize-handle-h" onMouseDown={handlePortfolioResize} />

                <div style={{ flex: 1, minWidth: 0, minHeight: 0, height: '100%', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
                  <SignalLog />
                </div>
              </>
            )}
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
            minHeight: 0,
            height: '100%',
            display: 'flex',
            flexDirection: 'column',
            gap: 12,
            overflow: 'hidden',
          }}>
            <div style={{ flex: fusionCollapsed ? '0 0 auto' : '1 1 0', minHeight: fusionCollapsed ? undefined : 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
              <FusionPanel
                instrument={instrument}
                isCollapsed={fusionCollapsed}
                onToggleCollapse={handleToggleFusionCollapsed}
              />
            </div>
            <div style={{ flex: newsCollapsed ? '0 0 auto' : '1 1 0', minHeight: newsCollapsed ? undefined : 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
              <NewsFeed
                isCollapsed={newsCollapsed}
                onToggleCollapse={handleToggleNewsCollapsed}
              />
            </div>
            <div style={{ flex: configCollapsed ? '0 0 auto' : '0 1 auto', minHeight: configCollapsed ? undefined : 0, maxHeight: configCollapsed ? undefined : '40%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
              <ConfigEditor
                instrument={instrument}
                isCollapsed={configCollapsed}
                onToggleCollapse={handleToggleConfigCollapsed}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
