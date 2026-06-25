import { useEffect, useRef } from 'react';
import { createSeriesMarkers } from 'lightweight-charts';
import type { ISeriesApi, ISeriesMarkersPluginApi, SeriesMarker, Time } from 'lightweight-charts';
import type { TradeSignal } from '../../types';

interface Props {
  candleSeries: ISeriesApi<'Candlestick'> | null;
  tradeSignals: TradeSignal[];
  instrument: string;
}

function toChartTime(iso: string): Time {
  return Math.floor(new Date(iso).getTime() / 1000) as Time;
}

export function SignalOverlay({ candleSeries, tradeSignals, instrument }: Props) {
  const markersPluginRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);

  // Attach/detach markers plugin when series changes
  useEffect(() => {
    if (!candleSeries) {
      markersPluginRef.current = null;
      return;
    }

    const plugin = createSeriesMarkers(candleSeries, []);
    markersPluginRef.current = plugin;

    return () => {
      plugin.setMarkers([]);
      markersPluginRef.current = null;
    };
  }, [candleSeries]);

  // Update markers when signals or instrument change
  useEffect(() => {
    const plugin = markersPluginRef.current;
    if (!plugin) return;

    const markers: SeriesMarker<Time>[] = tradeSignals
      .filter((s) => s.instrument?.toUpperCase() === instrument.toUpperCase())
      .slice(-50)
      .map((signal) => {
        const isLong = signal.direction === 'long' || signal.suggested_side === 'buy';
        const isShort = signal.direction === 'short' || signal.suggested_side === 'sell';
        return {
          time: toChartTime(signal.timestamp),
          position: isLong ? 'belowBar' : 'aboveBar',
          color: isLong ? '#00e676' : isShort ? '#ff1744' : '#8e9bb4',
          shape: isLong ? 'arrowUp' : isShort ? 'arrowDown' : 'circle',
          text: signal.direction?.toUpperCase() ?? 'SIG',
        };
      });

    plugin.setMarkers(markers);
  }, [candleSeries, tradeSignals, instrument]);

  return null;
}