import { useCallback, useEffect, useRef, useState } from 'react';
import type { IChartApi, ISeriesApi, Time } from 'lightweight-charts';
import { getOHLCV } from '../../../api/client';
import {
  LOOKBACK,
  MAX_BUFFER,
  applyChartViewport,
  filterChartBars,
  isTradingBar,
  type ChartViewportMode,
} from '../utils';
import { emitChartBarsUpdated } from '../../../utils/chartStatusEvents';
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

const LIVE_GAP_REFETCH_MS: Record<string, number> = {
  '1m': 60_000,
  '5m': 120_000,
  '15m': 180_000,
};
const DEFAULT_LIVE_GAP_REFETCH_MS = 180_000;

const MIN_BARS_FOR_LOAD: Record<string, number> = {
  '1m': 500,
  '5m': 200,
  '15m': 150,
};
const DEFAULT_MIN_BARS = 100;

function mergeBars(existing: any[], incoming: any[]): any[] {
  const uniqueMap = new Map<number, any>();
  for (const item of existing) uniqueMap.set(item.time, item);
  for (const item of incoming) uniqueMap.set(item.time, item);
  return Array.from(uniqueMap.values()).sort((a, b) => a.time - b.time);
}

export function useChartDataStream(
  chart: IChartApi | null,
  candleSeries: ISeriesApi<'Candlestick'> | null,
  volumeSeries: ISeriesApi<'Histogram'> | null,
  options: DataStreamHookOptions
) {
  const { instrument, timeframe, onNewBar, virtualEndTime, viewportMode = 'auto' } = options;

  const dataRef = useRef<any[]>([]);
  const barTimesRef = useRef<number[]>([]);

  const syncBarTimes = () => {
    barTimesRef.current = dataRef.current.map((d) => d.time);
  };

  const paginationRef = useRef({
    isFetching: false,
    hasMoreHistory: true,
    hasNewerHistory: false,
  });

  const candleSeriesRef = useRef(candleSeries);
  const volumeSeriesRef = useRef(volumeSeries);
  const chartRef = useRef(chart);
  const gapRefetchInFlightRef = useRef(false);

  useEffect(() => { candleSeriesRef.current = candleSeries; }, [candleSeries]);
  useEffect(() => { volumeSeriesRef.current = volumeSeries; }, [volumeSeries]);
  useEffect(() => { chartRef.current = chart; }, [chart]);

  const [reloadKey, setReloadKey] = useState(0);
  const prevVirtualEndTimeRef = useRef<string | undefined>(virtualEndTime);
  const virtualEndTimeRef = useRef(virtualEndTime);

  useEffect(() => {
    virtualEndTimeRef.current = virtualEndTime;
  }, [virtualEndTime]);

  const isReplayMode = () => virtualEndTimeRef.current !== undefined;

  const shouldFollowLive = useCallback((): boolean => {
    const c = chartRef.current;
    if (!c) return true;
    const range = c.timeScale().getVisibleLogicalRange();
    if (!range) return true;
    const lastIdx = dataRef.current.length - 1;
    return range.to >= lastIdx - 8;
  }, []);

  const applyBarsToSeries = useCallback((bars: any[], followLive = false) => {
    const cs = candleSeriesRef.current;
    const vs = volumeSeriesRef.current;
    const c = chartRef.current;
    if (!cs || !vs) return;

    const sanitized = filterChartBars(bars, { instrument });
    dataRef.current = sanitized;
    syncBarTimes();

    cs.setData(sanitized.map((d) => ({
      time: d.time as Time,
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
    })));
    vs.setData(sanitized.map((d) => ({
      time: d.time as Time,
      value: d.volume ?? 0,
      color: d.close >= d.open ? 'rgba(0,230,118,0.3)' : 'rgba(255,23,68,0.3)',
    })));

    if (followLive && c && !isReplayMode()) {
      applyChartViewport(c, sanitized, timeframe, { mode: viewportMode });
    }

    emitChartBarsUpdated(instrument, timeframe, sanitized);
  }, [timeframe, viewportMode, instrument]);

  const refetchRecentGap = useCallback(async (fromUnixSec: number, followLive = false) => {
    if (gapRefetchInFlightRef.current || isReplayMode()) return;
    gapRefetchInFlightRef.current = true;
    try {
      const lookbackDays = LOOKBACK[timeframe] ?? 30;
      const startMs = Math.min(fromUnixSec * 1000, Date.now() - lookbackDays * 86400_000);
      const start = new Date(startMs).toISOString();
      const end = new Date().toISOString();
      const chunk = await getOHLCV(instrument, timeframe, start, end);
      const filtered = filterChartBars(Array.isArray(chunk) ? chunk : [], {
        replayMode: false,
        instrument,
      });
      if (filtered.length === 0) return;

      const merged = mergeBars(dataRef.current, filtered);
      const finalData =
        merged.length > MAX_BUFFER ? merged.slice(merged.length - MAX_BUFFER) : merged;
      if (merged.length > MAX_BUFFER) {
        paginationRef.current.hasMoreHistory = true;
      }
      paginationRef.current.hasNewerHistory = false;
      applyBarsToSeries(finalData, followLive);
    } catch (err) {
      console.error('Error backfilling chart gap:', err);
    } finally {
      gapRefetchInFlightRef.current = false;
    }
  }, [applyBarsToSeries, instrument, timeframe]);

  useEffect(() => {
    const wasDefined = prevVirtualEndTimeRef.current !== undefined;
    const isDefined = virtualEndTime !== undefined;

    let shouldReload = wasDefined !== isDefined;

    if (wasDefined && isDefined && prevVirtualEndTimeRef.current !== virtualEndTime) {
      const prevSec = Math.floor(new Date(prevVirtualEndTimeRef.current!).getTime() / 1000);
      const currSec = Math.floor(new Date(virtualEndTime!).getTime() / 1000);
      const diff = currSec - prevSec;
      const timeframeSeconds = TIMEFRAME_SECONDS[timeframe] || 60;
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

  useEffect(() => {
    if (!chart || !candleSeries || !volumeSeries) return;

    paginationRef.current = {
      isFetching: false,
      hasMoreHistory: true,
      hasNewerHistory: false,
    };

    const end = virtualEndTimeRef.current || new Date().toISOString();
    const anchorTime = virtualEndTimeRef.current
      ? Math.floor(new Date(virtualEndTimeRef.current).getTime() / 1000)
      : undefined;
    const replayMode = isReplayMode();

    const fetchWithLookback = (lookbackDays: number, attempt: number) => {
      const endDate = new Date(end);
      const start = new Date(endDate.getTime() - lookbackDays * 86400_000).toISOString();

      getOHLCV(instrument, timeframe, start, end)
        .then((data: any[]) => {
          const filtered = filterChartBars(Array.isArray(data) ? data : [], { replayMode, instrument });

          const minBars = MIN_BARS_FOR_LOAD[timeframe] ?? DEFAULT_MIN_BARS;
          if (filtered.length < minBars && attempt < 3) {
            fetchWithLookback(lookbackDays + 5, attempt + 1);
            return;
          }

          if (filtered.length === 0) {
            paginationRef.current.hasMoreHistory = false;
            return;
          }

          const sortedUnique = mergeBars([], filtered);
          const finalData =
            sortedUnique.length > MAX_BUFFER
              ? sortedUnique.slice(sortedUnique.length - MAX_BUFFER)
              : sortedUnique;

          if (sortedUnique.length > MAX_BUFFER) {
            paginationRef.current.hasMoreHistory = true;
          }

          applyBarsToSeries(finalData);
          applyChartViewport(chart, finalData, timeframe, { mode: viewportMode, anchorTime });

          if (!replayMode) {
            const last = finalData[finalData.length - 1];
            if (last) {
              const ageSec = Math.floor(Date.now() / 1000) - last.time;
              const tfSec = TIMEFRAME_SECONDS[timeframe] || 3600;
              if (ageSec > tfSec * 2) {
                void refetchRecentGap(last.time, true);
              }
            }
          }
        })
        .catch(console.error);
    };

    const lookbackDays = LOOKBACK[timeframe] ?? 30;
    fetchWithLookback(lookbackDays, 1);
  }, [chart, candleSeries, volumeSeries, instrument, timeframe, reloadKey, applyBarsToSeries, refetchRecentGap, viewportMode]);

  useEffect(() => {
    if (!chart || dataRef.current.length === 0) return;
    const anchorTime = virtualEndTimeRef.current
      ? Math.floor(new Date(virtualEndTimeRef.current).getTime() / 1000)
      : undefined;
    applyChartViewport(chart, dataRef.current, timeframe, { mode: viewportMode, anchorTime });
  }, [chart, timeframe, viewportMode]);

  useEffect(() => {
    if (virtualEndTime) return;
    const pollMs = LIVE_GAP_REFETCH_MS[timeframe] ?? DEFAULT_LIVE_GAP_REFETCH_MS;
    const id = window.setInterval(() => {
      const last = dataRef.current[dataRef.current.length - 1];
      if (last) void refetchRecentGap(last.time, shouldFollowLive());
    }, pollMs);
    return () => window.clearInterval(id);
  }, [virtualEndTime, timeframe, refetchRecentGap, shouldFollowLive]);

  const updateBar = useCallback((bar: any) => {
    const cs = candleSeriesRef.current;
    const vs = volumeSeriesRef.current;
    if (!cs || !vs) return;
    if (!isTradingBar(bar, { instrument })) return;

    const barTime = typeof bar.time === 'number' ? bar.time : Number(bar.time);
    if (!Number.isFinite(barTime) || barTime <= 0) return;

    const pag = paginationRef.current;
    const tfSec = TIMEFRAME_SECONDS[timeframe] || 3600;

    if (virtualEndTimeRef.current) {
      const replayEndSec = Math.floor(new Date(virtualEndTimeRef.current).getTime() / 1000);
      if (barTime > replayEndSec + tfSec) return;
    }

    const lastBar = dataRef.current.length > 0 ? dataRef.current[dataRef.current.length - 1] : null;

    if (!virtualEndTimeRef.current && lastBar && barTime - lastBar.time > tfSec * 2) {
      void refetchRecentGap(lastBar.time, shouldFollowLive());
    }

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

    dataRef.current = filterChartBars(dataRef.current, { instrument });
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
      syncBarTimes();
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

    if (!virtualEndTimeRef.current && touchesLastBar && shouldFollowLive() && chartRef.current) {
      applyChartViewport(chartRef.current, dataRef.current, timeframe, { mode: viewportMode });
    }

    if (dataRef.current.length > 0) {
      emitChartBarsUpdated(instrument, timeframe, dataRef.current);
    }
  }, [instrument, timeframe, viewportMode, refetchRecentGap, shouldFollowLive]);

  useChartScrolling({
    chart,
    candleSeries,
    volumeSeries,
    instrument,
    timeframe,
    virtualEndTimeRef,
    dataRef,
    syncBarTimes,
    paginationRef,
  });

  useChartWebSocket({
    instrument,
    timeframe,
    onNewBar,
    updateBar,
    virtualEndTimeRef,
  });

  return { barTimesRef };
}