import { useEffect, useState } from 'react';
import type { RefObject } from 'react';
import { createChart, CandlestickSeries, HistogramSeries } from 'lightweight-charts';
import type { IChartApi, ISeriesApi } from 'lightweight-charts';
import { createChartTimezoneFormatters } from '../../../utils/chartTimezone';

export function useLightweightChart(
  containerRef: RefObject<HTMLDivElement | null>,
  timezone: string,
) {
  const [chartState, setChartState] = useState<{
    chart: IChartApi | null;
    candleSeries: ISeriesApi<'Candlestick'> | null;
    volumeSeries: ISeriesApi<'Histogram'> | null;
  }>({ chart: null, candleSeries: null, volumeSeries: null });

  useEffect(() => {
    if (!containerRef.current) return;

    const { timeFormatter, tickMarkFormatter } = createChartTimezoneFormatters(timezone);

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
      localization: { timeFormatter },
      timeScale: {
        borderColor: 'rgba(255,255,255,0.08)',
        timeVisible: true,
        tickMarkFormatter,
      },
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

  const { chart } = chartState;

  useEffect(() => {
    if (!chart) return;
    const { timeFormatter, tickMarkFormatter } = createChartTimezoneFormatters(timezone);
    chart.applyOptions({
      localization: { timeFormatter },
      timeScale: { tickMarkFormatter },
    });
  }, [chart, timezone]);

  return chartState;
}
