import { useEffect, useState } from 'react';
import type { RefObject } from 'react';
import { createChart, CandlestickSeries, HistogramSeries } from 'lightweight-charts';
import type { IChartApi, ISeriesApi } from 'lightweight-charts';

export function useLightweightChart(containerRef: RefObject<HTMLDivElement | null>) {
  const [chartState, setChartState] = useState<{
    chart: IChartApi | null;
    candleSeries: ISeriesApi<'Candlestick'> | null;
    volumeSeries: ISeriesApi<'Histogram'> | null;
  }>({ chart: null, candleSeries: null, volumeSeries: null });

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth || 1,
      height: containerRef.current.clientHeight || 1,
      autoSize: false,
      layout: { background: { color: '#0d1322' }, textColor: '#8e9bb4' },
      grid: {
        vertLines: { visible: false },
        horzLines: { color: 'rgba(255,255,255,0.03)' },
      },
      crosshair: { mode: 1 },
      timeScale: { borderColor: 'rgba(255,255,255,0.08)', timeVisible: true },
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#00e676', downColor: '#ff1744',
      borderUpColor: '#00e676', borderDownColor: '#ff1744',
      wickUpColor: '#00e676', wickDownColor: '#ff1744',
    });

    const volumeSeries = chart.addSeries(HistogramSeries, {
      color: '#00e5ff',
      priceFormat: { type: 'volume' },
      priceScaleId: '',
      lastValueVisible: false,
      priceLineVisible: false,
    });
    volumeSeries.priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });

    setChartState({ chart, candleSeries, volumeSeries });

    return () => {
      try { chart.remove(); } catch { /* ignore */ }
      setChartState({ chart: null, candleSeries: null, volumeSeries: null });
    };
  }, [containerRef]);

  return chartState;
}
