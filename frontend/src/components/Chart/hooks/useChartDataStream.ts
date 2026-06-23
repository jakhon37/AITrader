import { useEffect, useRef, useState } from 'react';
import type { IChartApi, ISeriesApi, Time } from 'lightweight-charts';
import { getOHLCV } from '../../../api/client';
import { LOOKBACK, MAX_BUFFER, findClosestIndex, isTradingBar } from '../utils';
import { useChartScrolling } from './useChartScrolling';
import { useChartWebSocket } from './useChartWebSocket';

interface DataStreamHookOptions {
  instrument: string;
  timeframe: string;
  onNewBar?: (bar: any) => void;
  virtualEndTime?: string;
}

// Global scroll cache to preserve zoom/pan position when changing timeframe/instrument
const lastScrollCache = {
  rightOffset: null as number | null,
  width: 150,
};
const prevTimeframeCache = { current: '' };
const prevInstrumentCache = { current: '' };

const TIMEFRAME_SECONDS: Record<string, number> = {
  '1m': 60,
  '5m': 300,
  '15m': 900,
  '30m': 1800,
  '1h': 3600,
  '4h': 14400,
  '1d': 86400,
  '1w': 604800,
};

export function useChartDataStream(
  chart: IChartApi | null,
  candleSeries: ISeriesApi<'Candlestick'> | null,
  volumeSeries: ISeriesApi<'Histogram'> | null,
  options: DataStreamHookOptions
) {
  const { instrument, timeframe, onNewBar, virtualEndTime } = options;

  const dataRef = useRef<any[]>([]);
  const paginationRef = useRef({
    isFetching: false,
    hasMoreHistory: true,
    hasNewerHistory: false,
  });

  const [reloadKey, setReloadKey] = useState(0);
  const prevVirtualEndTimeRef = useRef<string | undefined>(virtualEndTime);
  const virtualEndTimeRef = useRef(virtualEndTime);

  // Sync ref with option value
  useEffect(() => {
    virtualEndTimeRef.current = virtualEndTime;
  }, [virtualEndTime]);

  // Watch for mode transitions or manual slider jumps to trigger a reload
  useEffect(() => {
    const wasDefined = prevVirtualEndTimeRef.current !== undefined;
    const isDefined = virtualEndTime !== undefined;

    let shouldReload = wasDefined !== isDefined;

    if (wasDefined && isDefined && prevVirtualEndTimeRef.current !== virtualEndTime) {
      const prevSec = Math.floor(new Date(prevVirtualEndTimeRef.current!).getTime() / 1000);
      const currSec = Math.floor(new Date(virtualEndTime!).getTime() / 1000);
      const diff = currSec - prevSec;
      const timeframeSeconds = TIMEFRAME_SECONDS[timeframe] || 60;
      // If time went backward, or jumped forward by more than 10 bars or 3 days (e.g. manual slider jump or session restart)
      // Capping the minimum at 3 days prevents weekend gaps (~2.5 days) from triggering false reload jumps.
      const threshold = Math.max(10 * timeframeSeconds, 3 * 86400);
      if (diff < 0 || diff > threshold) {
        shouldReload = true;
      }
    }

    prevVirtualEndTimeRef.current = virtualEndTime;

    if (shouldReload) {
      setReloadKey((prev) => prev + 1);
    }
  }, [virtualEndTime, timeframe]);

  // 1. Initial Load & Timeframe Change scroll coordination
  useEffect(() => {
    if (!chart || !candleSeries || !volumeSeries) return;

    // Reset pagination state
    paginationRef.current = {
      isFetching: false,
      hasMoreHistory: true,
      hasNewerHistory: false,
    };

    if (prevInstrumentCache.current !== instrument) {
      lastScrollCache.rightOffset = null;
      prevInstrumentCache.current = instrument;
    }

    const isTimeframeChange = prevTimeframeCache.current !== timeframe;
    const end = virtualEndTimeRef.current || new Date().toISOString();

    if (!isTimeframeChange) {
      lastScrollCache.rightOffset = null;
    }

    prevTimeframeCache.current = timeframe;

    const days = LOOKBACK[timeframe] ?? 30;
    const endDate = new Date(end);
    const start = new Date(endDate.getTime() - days * 86400_000).toISOString();

    getOHLCV(instrument, timeframe, start, end)
      .then((data: any[]) => {
        if (!Array.isArray(data) || data.length === 0) {
          paginationRef.current.hasMoreHistory = false;
          return;
        }

        const filtered = data.filter(isTradingBar);
        if (filtered.length > MAX_BUFFER) {
          dataRef.current = filtered.slice(filtered.length - MAX_BUFFER);
          paginationRef.current.hasMoreHistory = true;
        } else {
          dataRef.current = filtered;
        }

        candleSeries.setData(dataRef.current.map((d) => ({ time: d.time as Time, open: d.open, high: d.high, low: d.low, close: d.close })));
        volumeSeries.setData(dataRef.current.map((d) => ({ time: d.time as Time, value: d.volume ?? 0, color: d.close >= d.open ? 'rgba(0,230,118,0.3)' : 'rgba(255,23,68,0.3)' })));

        if (isTimeframeChange && lastScrollCache.rightOffset !== null) {
          const newLastIndex = dataRef.current.length - 1;
          const newTo = newLastIndex + lastScrollCache.rightOffset;
          const newFrom = newTo - lastScrollCache.width;
          chart.timeScale().setVisibleLogicalRange({
            from: newFrom,
            to: newTo,
          });
        } else {
          chart.timeScale().fitContent();
        }
      })
      .catch(console.error);

    return () => {
      try {
        const logicalRange = chart.timeScale().getVisibleLogicalRange();
        if (logicalRange) {
          const width = logicalRange.to - logicalRange.from;
          const lastIndex = dataRef.current.length - 1;
          lastScrollCache.rightOffset = logicalRange.to - lastIndex;
          lastScrollCache.width = width;
        }
      } catch (e) {
        /* ignore */
      }
    };
  }, [chart, candleSeries, volumeSeries, instrument, timeframe, reloadKey]);

  // 2. Active updating bar closure
  const updateBar = (bar: any) => {
    if (!candleSeries || !volumeSeries) return;
    if (!isTradingBar(bar)) return;

    const pag = paginationRef.current;

    if (pag.hasNewerHistory) {
      const idx = dataRef.current.findIndex((d) => d.time === bar.time);
      if (idx !== -1) {
        dataRef.current[idx] = bar;
        candleSeries.update({ time: bar.time as Time, open: bar.open, high: bar.high, low: bar.low, close: bar.close });
        volumeSeries.update({
          time: bar.time as Time,
          value: bar.volume,
          color: bar.close >= bar.open ? 'rgba(0,230,118,0.3)' : 'rgba(255,23,68,0.3)',
        });
      }
      return;
    }

    candleSeries.update({ time: bar.time as Time, open: bar.open, high: bar.high, low: bar.low, close: bar.close });
    volumeSeries.update({
      time: bar.time as Time,
      value: bar.volume,
      color: bar.close >= bar.open ? 'rgba(0,230,118,0.3)' : 'rgba(255,23,68,0.3)',
    });

    const idx = dataRef.current.findIndex((d) => d.time === bar.time);
    if (idx !== -1) {
      dataRef.current[idx] = bar;
    } else {
      dataRef.current.push(bar);
      dataRef.current.sort((a, b) => a.time - b.time);
      if (dataRef.current.length > MAX_BUFFER) {
        dataRef.current = dataRef.current.slice(dataRef.current.length - MAX_BUFFER);
        pag.hasMoreHistory = true;
        candleSeries.setData(dataRef.current.map((d) => ({ time: d.time as Time, open: d.open, high: d.high, low: d.low, close: d.close })));
        volumeSeries.setData(dataRef.current.map((d) => ({ time: d.time as Time, value: d.volume ?? 0, color: d.close >= d.open ? 'rgba(0,230,118,0.3)' : 'rgba(255,23,68,0.3)' })));
      }
    }
  };

  // 3. Mount Scroll Pagination Hook
  useChartScrolling({
    chart,
    candleSeries,
    volumeSeries,
    instrument,
    timeframe,
    virtualEndTimeRef,
    dataRef,
    paginationRef,
  });

  // 4. Mount WebSocket Feeds Hook
  useChartWebSocket({
    instrument,
    timeframe,
    onNewBar,
    updateBar,
  });
}
