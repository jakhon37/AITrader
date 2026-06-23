import { useRef } from 'react';
import { useLightweightChart, useChartDataStream } from './hooks';

interface Props {
  instrument: string;
  timeframe: string;
  onNewBar?: (bar: { time: number; open: number; high: number; low: number; close: number; volume: number }) => void;
  virtualEndTime?: string; // ISO string representing active replay timestamp
}

export function CandleChart({ instrument, timeframe, onNewBar, virtualEndTime }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  
  // Custom hook to initialize lightweight-chart canvas and series, and handle resize observer
  const { chart, candleSeries, volumeSeries } = useLightweightChart(containerRef);

  // Custom hook to handle initial fetch, pagination, window scroll events, and websocket/replay feeds
  useChartDataStream(chart, candleSeries, volumeSeries, {
    instrument,
    timeframe,
    onNewBar,
    virtualEndTime,
  });

  return <div ref={containerRef} style={{ width: '100%', height: '100%' }} />;
}
