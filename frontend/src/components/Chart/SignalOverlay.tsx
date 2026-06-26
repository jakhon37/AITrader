import { useEffect, useRef } from 'react';
import { createSeriesMarkers } from 'lightweight-charts';
import type { ISeriesApi, ISeriesMarkersPluginApi, SeriesMarker, Time } from 'lightweight-charts';
import type { ChartMarker } from '../../types';

interface Props {
  candleSeries: ISeriesApi<'Candlestick'> | null;
  chartMarkers: ChartMarker[];
  instrument: string;
}

function toChartTime(iso: string): Time {
  return Math.floor(new Date(iso).getTime() / 1000) as Time;
}

function instrumentKey(value: string | { value?: string } | undefined): string {
  if (!value) return '';
  if (typeof value === 'string') return value.toUpperCase();
  return String(value.value ?? '').toUpperCase();
}

export function SignalOverlay({ candleSeries, chartMarkers, instrument }: Props) {
  const markersPluginRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);

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

  useEffect(() => {
    const plugin = markersPluginRef.current;
    if (!plugin) return;

    const inst = instrument.toUpperCase();
    const markers: SeriesMarker<Time>[] = chartMarkers
      .filter((m) => instrumentKey(m.instrument) === inst)
      .filter((m) => m.direction === 'long' || m.direction === 'short')
      .map((marker) => {
        const isLong = marker.direction === 'long';
        return {
          time: toChartTime(marker.bar_time),
          position: isLong ? 'belowBar' : 'aboveBar',
          color: isLong ? '#00e676' : '#ff1744',
          shape: isLong ? 'arrowUp' : 'arrowDown',
          text: isLong ? 'LONG' : 'SHORT',
        };
      });

    plugin.setMarkers(markers);
  }, [candleSeries, chartMarkers, instrument]);

  return null;
}