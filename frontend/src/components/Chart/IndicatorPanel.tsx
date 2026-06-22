import { useEffect, useRef } from 'react';
import { createChart, LineSeries, HistogramSeries } from 'lightweight-charts';
import type { IChartApi, Time } from 'lightweight-charts';
import { useSignalsStore } from '../../store/signals';

export function IndicatorPanel() {
  const technicalSignal = useSignalsStore((s) => s.technicalSignal);
  const rsiRef = useRef<HTMLDivElement>(null);
  const macdRef = useRef<HTMLDivElement>(null);
  const rsiChartRef = useRef<IChartApi | null>(null);
  const macdChartRef = useRef<IChartApi | null>(null);

  const chartOpts = {
    layout: { background: { color: '#0a0f1a' }, textColor: '#57657e' },
    grid: { vertLines: { visible: false }, horzLines: { color: 'rgba(255,255,255,0.02)' } },
    timeScale: { borderColor: 'rgba(255,255,255,0.05)', timeVisible: false },
    rightPriceScale: { borderColor: 'rgba(255,255,255,0.05)' },
  };

  useEffect(() => {
    if (!rsiRef.current || !macdRef.current) return;
    if (rsiChartRef.current) { try { rsiChartRef.current.remove(); } catch { /**/ } }
    if (macdChartRef.current) { try { macdChartRef.current.remove(); } catch { /**/ } }

    const rsiChart = createChart(rsiRef.current, { ...chartOpts, width: rsiRef.current.clientWidth, height: rsiRef.current.clientHeight });
    const rsiSeries = rsiChart.addSeries(LineSeries, { color: '#00e5ff', lineWidth: 1 });
    rsiChart.addSeries(LineSeries, { color: 'rgba(255,100,100,0.4)', lineWidth: 1 }); // 70 line
    rsiChart.addSeries(LineSeries, { color: 'rgba(100,255,100,0.4)', lineWidth: 1 }); // 30 line
    rsiChartRef.current = rsiChart;

    const macdChart = createChart(macdRef.current, { ...chartOpts, width: macdRef.current.clientWidth, height: macdRef.current.clientHeight });
    macdChart.addSeries(HistogramSeries, { color: '#00e676' });
    macdChartRef.current = macdChart;

    if (technicalSignal?.per_timeframe?.length) {
      const indicators = technicalSignal.per_timeframe[0].indicators;
      const now = Math.floor(Date.now() / 1000) as Time;
      const rsi = indicators['rsi'];
      if (rsi !== undefined) {
        rsiSeries.setData([{ time: now, value: rsi }]);
      }
    }

    const ro = new ResizeObserver((entries) => {
      if (!entries[0]) return;
      const { width } = entries[0].contentRect;
      rsiChartRef.current?.resize(width, rsiRef.current?.clientHeight ?? 80);
      macdChartRef.current?.resize(width, macdRef.current?.clientHeight ?? 80);
    });
    if (rsiRef.current) ro.observe(rsiRef.current);

    return () => {
      ro.disconnect();
      try { rsiChart.remove(); } catch { /**/ }
      try { macdChart.remove(); } catch { /**/ }
    };
  }, [technicalSignal]);

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, height: '100%' }}>
      <div className="glass-panel" style={{ padding: 8, display: 'flex', flexDirection: 'column' }}>
        <span style={{ fontSize: 10, color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 4 }}>RSI</span>
        <div ref={rsiRef} style={{ flex: 1 }} />
      </div>
      <div className="glass-panel" style={{ padding: 8, display: 'flex', flexDirection: 'column' }}>
        <span style={{ fontSize: 10, color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 4 }}>MACD</span>
        <div ref={macdRef} style={{ flex: 1 }} />
      </div>
    </div>
  );
}
