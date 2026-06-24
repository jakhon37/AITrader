import { useCallback, useEffect, useRef, useState } from 'react';
import type { IChartApi, ISeriesApi, Time } from 'lightweight-charts';
import { getOHLCV } from '../../../api/client';
import { LOOKBACK, MAX_BUFFER, applyChartViewport, isTradingBar, type ChartViewportMode } from '../utils';
import { useChartScrolling } from './useChartScrolling';
import { useChartWebSocket } from './useChartWebSocket';

interface DataStreamHookOptions {
  instrument: string;
  timeframe: string;
  onNewBar?: (bar: any) => void;
  virtualEndTime?: string;
  /** How the chart adjusts its visible range after load / timeframe change. Default: auto. */
  viewportMode?: ChartViewportMode;
}

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
  const { instrument, timeframe, onNewBar, virtualEndTime, viewportMode = 'auto' } = options;

  const dataRef = useRef<any[]>([]);
  const paginationRef = useRef({
    isFetching: false,
    hasMoreHistory: true,
    hasNewerHistory: false,
  });

  // Keep stable refs to the series so updateBar never becomes stale
  const candleSeriesRef = useRef(candleSeries);
  const volumeSeriesRef = useRef(volumeSeries);
  useEffect(() => { candleSeriesRef.current = candleSeries; }, [candleSeries]);
  useEffect(() => { volumeSeriesRef.current = volumeSeries; }, [volumeSeries]);

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

    const end = virtualEndTimeRef.current || new Date().toISOString();
    const anchorTime = virtualEndTimeRef.current
      ? Math.floor(new Date(virtualEndTimeRef.current).getTime() / 1000)
      : undefined;

    const fetchWithLookback = (lookbackDays: number, attempt: number) => {
      const endDate = new Date(end);
      const start = new Date(endDate.getTime() - lookbackDays * 86400_000).toISOString();

      getOHLCV(instrument, timeframe, start, end)
        .then((data: any[]) => {
          const filtered = Array.isArray(data) ? data.filter(isTradingBar) : [];

          if (filtered.length < 100 && attempt < 3) {
            // No or too few data in this window (e.g. start date is weekend/holiday).
            // Try again recursively with a larger lookback window (adding 5 days).
            fetchWithLookback(lookbackDays + 5, attempt + 1);
            return;
          }

          if (filtered.length === 0) {
            paginationRef.current.hasMoreHistory = false;
            return;
          }

          // Deduplicate and sort ascending by time
          const uniqueMap = new Map<number, any>();
          for (const item of filtered) {
            uniqueMap.set(item.time, item);
          }
          const sortedUnique = Array.from(uniqueMap.values()).sort((a, b) => a.time - b.time);

          if (sortedUnique.length > MAX_BUFFER) {
            dataRef.current = sortedUnique.slice(sortedUnique.length - MAX_BUFFER);
            paginationRef.current.hasMoreHistory = true;
          } else {
            dataRef.current = sortedUnique;
          }

          candleSeries.setData(dataRef.current.map((d) => ({ time: d.time as Time, open: d.open, high: d.high, low: d.low, close: d.close })));
          volumeSeries.setData(dataRef.current.map((d) => ({ time: d.time as Time, value: d.volume ?? 0, color: d.close >= d.open ? 'rgba(0,230,118,0.3)' : 'rgba(255,23,68,0.3)' })));

          applyChartViewport(chart, dataRef.current, timeframe, {
            mode: viewportMode,
            anchorTime,
          });
        })
        .catch(console.error);
    };

    const lookbackDays = LOOKBACK[timeframe] ?? 30;
    fetchWithLookback(lookbackDays, 1);
  }, [chart, candleSeries, volumeSeries, instrument, timeframe, reloadKey]);

  // Re-apply viewport when the user toggles zoom mode without refetching data
  useEffect(() => {
    if (!chart || dataRef.current.length === 0) return;
    const anchorTime = virtualEndTimeRef.current
      ? Math.floor(new Date(virtualEndTimeRef.current).getTime() / 1000)
      : undefined;
    applyChartViewport(chart, dataRef.current, timeframe, { mode: viewportMode, anchorTime });
  }, [chart, timeframe, viewportMode]);

  // 2. Active updating bar closure — stable via useCallback + series refs
  const updateBar = useCallback((bar: any) => {
    const cs = candleSeriesRef.current;
    const vs = volumeSeriesRef.current;
    if (!cs || !vs) return;
    if (!isTradingBar(bar)) return;

    // Guarantee time is a plain integer Unix seconds (never an object)
    const barTime = typeof bar.time === 'number' ? bar.time : Number(bar.time);
    if (!Number.isFinite(barTime) || barTime <= 0) return;

    const pag = paginationRef.current;

    // During replay, reject live-scheduler bars that leaked in with timestamps
    // beyond the simulation clock — they become the series "last" bar and freeze
    // the price-line indicator.
    if (virtualEndTimeRef.current) {
      const replayEndSec = Math.floor(new Date(virtualEndTimeRef.current).getTime() / 1000);
      const tfSec = TIMEFRAME_SECONDS[timeframe] || 3600;
      if (barTime > replayEndSec + tfSec) return;
    }

    const lastBar = dataRef.current.length > 0 ? dataRef.current[dataRef.current.length - 1] : null;
    const isUpdateLastOrNew = !lastBar || barTime >= lastBar.time;

    const idx = dataRef.current.findIndex((d) => d.time === barTime);
    if (idx !== -1) {
      dataRef.current[idx] = { ...bar, time: barTime };
    } else {
      dataRef.current.push({ ...bar, time: barTime });
      dataRef.current.sort((a, b) => a.time - b.time);
      if (dataRef.current.length > MAX_BUFFER) {
        dataRef.current = dataRef.current.slice(dataRef.current.length - MAX_BUFFER);
        pag.hasMoreHistory = true;
      }
    }

    const lastIdx = dataRef.current.length - 1;
    const touchesLastBar = idx === -1 ? barTime >= (dataRef.current[lastIdx]?.time ?? 0) : idx === lastIdx;

    const candleData = dataRef.current.map((d) => ({
      time: d.time as Time,
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
    }));
    const volumeData = dataRef.current.map((d) => ({
      time: d.time as Time,
      value: d.volume ?? 0,
      color: d.close >= d.open ? 'rgba(0,230,118,0.3)' : 'rgba(255,23,68,0.3)',
    }));

    const applySetData = () => {
      cs.setData(candleData);
      vs.setData(volumeData);
    };

    if (touchesLastBar && isUpdateLastOrNew && !pag.hasNewerHistory) {
      try {
        cs.update({ time: barTime as Time, open: bar.open, high: bar.high, low: bar.low, close: bar.close });
        vs.update({ time: barTime as Time, value: bar.volume, color: bar.close >= bar.open ? 'rgba(0,230,118,0.3)' : 'rgba(255,23,68,0.3)' });
      } catch {
        applySetData();
      }
    } else {
      try {
        applySetData();
      } catch { /* ignore */ }
    }
  }, [timeframe]); // timeframe for replay bar-time guard

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
    virtualEndTimeRef,
  });
}
