import { useEffect, useRef } from 'react';
import { createChart, LineSeries, type IChartApi, type ISeriesApi } from 'lightweight-charts';

interface EquityPoint {
  time: string;
  equity: number;
}

interface EquityCurveChartProps {
  data: EquityPoint[];
  initialCapital: number;
}

function toUnix(iso: string): number {
  return Math.floor(new Date(iso).getTime() / 1000);
}

/** lightweight-charts requires strictly ascending unique timestamps. */
function normalizeEquityPoints(
  data: EquityPoint[],
  initialCapital: number,
): { time: number; value: number }[] {
  const source =
    data.length > 0 ? data : [{ time: new Date().toISOString(), equity: initialCapital }];

  const byTime = new Map<number, number>();
  for (const point of source) {
    const time = toUnix(point.time);
    if (!Number.isFinite(time)) continue;
    byTime.set(time, point.equity);
  }

  return Array.from(byTime.entries())
    .sort(([a], [b]) => a - b)
    .map(([time, value]) => ({ time, value }));
}

export function EquityCurveChart({ data, initialCapital }: EquityCurveChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Line'> | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { color: '#0a0f1a' },
        textColor: '#8b9bb4',
      },
      grid: {
        vertLines: { color: 'rgba(255,255,255,0.04)' },
        horzLines: { color: 'rgba(255,255,255,0.04)' },
      },
      rightPriceScale: { borderColor: 'rgba(255,255,255,0.08)' },
      timeScale: { borderColor: 'rgba(255,255,255,0.08)' },
      crosshair: { mode: 1 },
      width: containerRef.current.clientWidth,
      height: containerRef.current.clientHeight,
    });

    const series = chart.addSeries(LineSeries, {
      color: '#00e5ff',
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
    });

    chartRef.current = chart;
    seriesRef.current = series;

    const ro = new ResizeObserver(() => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight,
        });
      }
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!seriesRef.current) return;
    const points = normalizeEquityPoints(data, initialCapital);
    if (points.length === 0) return;

    try {
      seriesRef.current.setData(points as any);
      chartRef.current?.timeScale().fitContent();
    } catch (err) {
      console.error('EquityCurveChart: failed to set data', err);
    }
  }, [data, initialCapital]);

  return (
    <div
      ref={containerRef}
      style={{ width: '100%', height: '100%', minHeight: 180, borderRadius: 8, overflow: 'hidden' }}
    />
  );
}