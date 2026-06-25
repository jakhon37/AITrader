import { useCallback, useEffect, useRef, useState } from 'react';
import { createChart, LineSeries, HistogramSeries } from 'lightweight-charts';
import type { IChartApi, ISeriesApi, Time } from 'lightweight-charts';
import { getOHLCV } from '../../api/client';
import { LOOKBACK, filterChartBars } from './utils';
import {
  computeMacdSeries,
  computeRsiSeries,
  latestMacd,
  latestRsi,
  type MacdPoint,
  type RsiPoint,
} from './indicators';

interface IndicatorPanelProps {
  instrument: string;
  timeframe: string;
}

const BASE_CHART_OPTS = {
  layout: { background: { color: '#0a0f1a' }, textColor: '#57657e' },
  grid: { vertLines: { visible: false }, horzLines: { color: 'rgba(255,255,255,0.04)' } },
  timeScale: { borderColor: 'rgba(255,255,255,0.05)', timeVisible: false, fixLeftEdge: true, fixRightEdge: true },
  rightPriceScale: { borderColor: 'rgba(255,255,255,0.05)' },
  crosshair: { mode: 1 as const },
  handleScroll: false,
  handleScale: false,
};

function refLineData(points: RsiPoint[], level: number) {
  if (points.length === 0) return [];
  return points.map((p) => ({ time: p.time as Time, value: level }));
}

export function IndicatorPanel({ instrument, timeframe }: IndicatorPanelProps) {
  const rsiRef = useRef<HTMLDivElement>(null);
  const macdRef = useRef<HTMLDivElement>(null);
  const rsiChartRef = useRef<IChartApi | null>(null);
  const macdChartRef = useRef<IChartApi | null>(null);
  const rsiSeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const rsiHighRef = useRef<ISeriesApi<'Line'> | null>(null);
  const rsiLowRef = useRef<ISeriesApi<'Line'> | null>(null);
  const macdHistRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const macdLineRef = useRef<ISeriesApi<'Line'> | null>(null);
  const macdSignalRef = useRef<ISeriesApi<'Line'> | null>(null);

  const [rsiLabel, setRsiLabel] = useState<string>('—');
  const [macdLabel, setMacdLabel] = useState<string>('—');
  const [loading, setLoading] = useState(false);

  const applySeries = useCallback((rsiPoints: RsiPoint[], macdPoints: MacdPoint[]) => {
    const rsiSeries = rsiSeriesRef.current;
    const rsiHigh = rsiHighRef.current;
    const rsiLow = rsiLowRef.current;
    const macdHist = macdHistRef.current;
    const macdLine = macdLineRef.current;
    const macdSignal = macdSignalRef.current;
    if (!rsiSeries || !rsiHigh || !rsiLow || !macdHist || !macdLine || !macdSignal) return;

    if (rsiPoints.length === 0) {
      rsiSeries.setData([]);
      rsiHigh.setData([]);
      rsiLow.setData([]);
      setRsiLabel('—');
    } else {
      rsiSeries.setData(rsiPoints.map((p) => ({ time: p.time as Time, value: p.value })));
      rsiHigh.setData(refLineData(rsiPoints, 70));
      rsiLow.setData(refLineData(rsiPoints, 30));
      const last = latestRsi(rsiPoints);
      setRsiLabel(last != null ? last.toFixed(1) : '—');
    }

    if (macdPoints.length === 0) {
      macdHist.setData([]);
      macdLine.setData([]);
      macdSignal.setData([]);
      setMacdLabel('—');
    } else {
      macdHist.setData(
        macdPoints.map((p) => ({
          time: p.time as Time,
          value: p.hist,
          color: p.hist >= 0 ? 'rgba(0,230,118,0.55)' : 'rgba(255,23,68,0.55)',
        })),
      );
      macdLine.setData(macdPoints.map((p) => ({ time: p.time as Time, value: p.macd })));
      macdSignal.setData(macdPoints.map((p) => ({ time: p.time as Time, value: p.signal })));
      const last = latestMacd(macdPoints);
      setMacdLabel(last != null ? last.hist.toFixed(5) : '—');
    }

    try {
      rsiChartRef.current?.timeScale().fitContent();
      macdChartRef.current?.timeScale().fitContent();
    } catch {
      /* disposed */
    }
  }, []);

  const loadIndicators = useCallback(async () => {
    setLoading(true);
    try {
      const lookbackDays = LOOKBACK[timeframe] ?? 30;
      const end = new Date().toISOString();
      const start = new Date(Date.now() - lookbackDays * 86400_000).toISOString();
      const raw = await getOHLCV(instrument, timeframe, start, end);
      const bars = filterChartBars(Array.isArray(raw) ? raw : [], { instrument })
        .map((b) => ({ time: b.time, close: b.close }))
        .sort((a, b) => a.time - b.time);
      applySeries(computeRsiSeries(bars), computeMacdSeries(bars));
    } catch {
      applySeries([], []);
    } finally {
      setLoading(false);
    }
  }, [applySeries, instrument, timeframe]);

  useEffect(() => {
    if (!rsiRef.current || !macdRef.current) return;

    const rsiChart = createChart(rsiRef.current, {
      ...BASE_CHART_OPTS,
      width: rsiRef.current.clientWidth || 1,
      height: rsiRef.current.clientHeight || 80,
    });
    const rsiSeries = rsiChart.addSeries(LineSeries, {
      color: '#00e5ff',
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
      crosshairMarkerVisible: true,
    });
    const rsiHigh = rsiChart.addSeries(LineSeries, {
      color: 'rgba(255,100,100,0.35)',
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });
    const rsiLow = rsiChart.addSeries(LineSeries, {
      color: 'rgba(100,255,100,0.35)',
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });
    rsiChart.priceScale('right').applyOptions({ autoScale: true, scaleMargins: { top: 0.08, bottom: 0.08 } });

    const macdChart = createChart(macdRef.current, {
      ...BASE_CHART_OPTS,
      width: macdRef.current.clientWidth || 1,
      height: macdRef.current.clientHeight || 80,
    });
    const macdHist = macdChart.addSeries(HistogramSeries, {
      priceLineVisible: false,
      lastValueVisible: false,
    });
    const macdLine = macdChart.addSeries(LineSeries, {
      color: '#00e5ff',
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
    });
    const macdSignal = macdChart.addSeries(LineSeries, {
      color: '#ff9100',
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
    });

    rsiChartRef.current = rsiChart;
    macdChartRef.current = macdChart;
    rsiSeriesRef.current = rsiSeries;
    rsiHighRef.current = rsiHigh;
    rsiLowRef.current = rsiLow;
    macdHistRef.current = macdHist;
    macdLineRef.current = macdLine;
    macdSignalRef.current = macdSignal;

    const ro = new ResizeObserver((entries) => {
      if (!entries[0]) return;
      const { width, height } = entries[0].contentRect;
      try {
        rsiChart.resize(width, Math.max(height, 40));
        macdChart.resize(width, Math.max(height, 40));
      } catch {
        /* disposed */
      }
    });
    ro.observe(rsiRef.current);

    return () => {
      ro.disconnect();
      rsiChartRef.current = null;
      macdChartRef.current = null;
      rsiSeriesRef.current = null;
      rsiHighRef.current = null;
      rsiLowRef.current = null;
      macdHistRef.current = null;
      macdLineRef.current = null;
      macdSignalRef.current = null;
      try { rsiChart.remove(); } catch { /**/ }
      try { macdChart.remove(); } catch { /**/ }
    };
  }, []);

  useEffect(() => {
    void loadIndicators();
  }, [loadIndicators]);

  useEffect(() => {
    const onBarsUpdated = (event: Event) => {
      const detail = (event as CustomEvent<{ instrument: string; timeframe: string }>).detail;
      if (!detail) return;
      if (detail.instrument.toUpperCase() !== instrument.toUpperCase()) return;
      if (detail.timeframe !== timeframe) return;
      void loadIndicators();
    };
    window.addEventListener('chart_bars_updated', onBarsUpdated);
    return () => window.removeEventListener('chart_bars_updated', onBarsUpdated);
  }, [instrument, timeframe, loadIndicators]);

  const muted = loading ? ' (loading…)' : '';

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, height: '100%', minHeight: 80 }}>
      <div className="glass-panel" style={{ padding: 8, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        <span style={{ fontSize: 10, color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 4 }}>
          RSI (14) <span style={{ color: 'var(--neon-cyan)', marginLeft: 6 }}>{rsiLabel}</span>
          <span style={{ opacity: 0.6, fontWeight: 400, marginLeft: 4 }}>{muted}</span>
        </span>
        <div ref={rsiRef} style={{ flex: 1, minHeight: 48 }} />
      </div>
      <div className="glass-panel" style={{ padding: 8, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        <span style={{ fontSize: 10, color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 4 }}>
          MACD <span style={{ color: 'var(--neon-cyan)', marginLeft: 6 }}>{macdLabel}</span>
          <span style={{ opacity: 0.6, fontWeight: 400, marginLeft: 4 }}>{muted}</span>
        </span>
        <div ref={macdRef} style={{ flex: 1, minHeight: 48 }} />
      </div>
    </div>
  );
}