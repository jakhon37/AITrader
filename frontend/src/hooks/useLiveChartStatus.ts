import { useCallback, useEffect, useState } from 'react';
import { getLiveStatus } from '../api/client';
import type { ChartBarsUpdatedDetail } from '../utils/chartStatusEvents';

/** Max age before scheduler poll is considered stale (scaled per timeframe). */
const POLL_STALE_MS: Record<string, number> = {
  '1m': 90_000,
  '5m': 180_000,
  '15m': 300_000,
  '30m': 420_000,
  '1h': 900_000,
  '4h': 3_600_000,
  '1d': 14_400_000,
};

const DEFAULT_POLL_STALE_MS = 120_000;
const WARMING_UP_MS = 30_000;

/** Bar open time can be up to ~1 full candle in the past while the chart is still live. */
const TIMEFRAME_SEC: Record<string, number> = {
  '1m': 60,
  '5m': 300,
  '15m': 900,
  '30m': 1800,
  '1h': 3600,
  '4h': 14400,
  '1d': 86400,
  '1w': 604800,
};

export type LiveChartStatus = {
  lastUpdate: Date | null;
  lastPollAt: Date | null;
  source: string | null;
  close: number | null;
  serverError: string | null;
  replayBlocked: boolean;
  dataFresh: boolean;
  pollFresh: boolean;
  warmingUp: boolean;
  feedOffline: boolean;
};

function mergeLatest(prev: Date | null, next: Date): Date {
  return !prev || next > prev ? next : prev;
}

export function useLiveChartStatus(
  instrument: string,
  timeframe: string,
  wsConnected: boolean,
): LiveChartStatus {
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const [lastPollAt, setLastPollAt] = useState<Date | null>(null);
  const [source, setSource] = useState<string | null>(null);
  const [close, setClose] = useState<number | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const [replayBlocked, setReplayBlocked] = useState(false);
  const [pollStaleMs, setPollStaleMs] = useState(DEFAULT_POLL_STALE_MS);
  const [schedulerRunning, setSchedulerRunning] = useState(false);
  const [focusedMatches, setFocusedMatches] = useState(false);
  const [hasPairPoll, setHasPairPoll] = useState(false);
  const [focusStartedAt, setFocusStartedAt] = useState(() => Date.now());
  const [tick, setTick] = useState(0);

  const applyDataPoint = useCallback((at: Date, price?: number) => {
    setLastUpdate((prev) => mergeLatest(prev, at));
    if (typeof price === 'number' && Number.isFinite(price)) {
      setClose(price);
    }
  }, []);

  useEffect(() => {
    setLastUpdate(null);
    setLastPollAt(null);
    setClose(null);
    setServerError(null);
    setHasPairPoll(false);
    setFocusStartedAt(Date.now());
  }, [instrument, timeframe]);

  useEffect(() => {
    const handleBar = (e: Event) => {
      const customEvent = e as CustomEvent<{
        instrument: string;
        timeframe: string;
        source?: string;
        bar: { close: number; time?: number };
      }>;
      const { instrument: barInst, timeframe: barTf, source: barSource, bar } = customEvent.detail;
      if (
        String(barInst).toUpperCase() === instrument.toUpperCase() &&
        String(barTf) === timeframe
      ) {
        const barTime =
          typeof bar.time === 'number' && bar.time > 0
            ? new Date(bar.time * 1000)
            : new Date();
        applyDataPoint(barTime, bar.close);
        setSource(barSource ?? 'dukascopy');
        setServerError(null);
      }
    };

    const handleChartBars = (e: Event) => {
      const { instrument: chartInst, timeframe: chartTf, lastBarAt, close: barClose } =
        (e as CustomEvent<ChartBarsUpdatedDetail>).detail;
      if (
        chartInst.toUpperCase() === instrument.toUpperCase() &&
        chartTf === timeframe
      ) {
        applyDataPoint(lastBarAt, barClose);
        setServerError(null);
      }
    };

    window.addEventListener('ohlcv_bar', handleBar);
    window.addEventListener('chart_bars_updated', handleChartBars);
    return () => {
      window.removeEventListener('ohlcv_bar', handleBar);
      window.removeEventListener('chart_bars_updated', handleChartBars);
    };
  }, [instrument, timeframe, applyDataPoint]);

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      try {
        const status = await getLiveStatus();
        if (cancelled) return;
        setReplayBlocked(Boolean(status.replay_active));
        setSchedulerRunning(Boolean(status.running));

        const pairKey = `${instrument.toUpperCase()}/${timeframe}`;
        const pair = status.pairs?.[pairKey] as
          | {
              last_error?: string;
              source?: string;
              close?: number;
              last_bar_at?: string;
              last_poll_at?: string;
            }
          | undefined;

        const focused = status.focused_pair as
          | { instrument: string; timeframe: string }
          | null
          | undefined;
        const matchesFocused =
          Boolean(focused) &&
          focused!.instrument.toUpperCase() === instrument.toUpperCase() &&
          focused!.timeframe === timeframe;
        setFocusedMatches(matchesFocused);

        const err = pair?.last_error ?? status.last_error ?? null;
        setServerError(err);
        if (pair?.source) setSource(pair.source);
        if (typeof pair?.close === 'number') setClose(pair.close);
        if (pair?.last_bar_at) {
          applyDataPoint(new Date(pair.last_bar_at));
        }

        const pairPoll = pair?.last_poll_at ? new Date(pair.last_poll_at) : null;
        setHasPairPoll(pairPoll !== null);
        setLastPollAt(pairPoll);

        const intervalSec =
          typeof status.focused_poll_interval_sec === 'number'
            ? status.focused_poll_interval_sec
            : null;
        if (matchesFocused && intervalSec !== null && intervalSec > 0) {
          setPollStaleMs(Math.max(45_000, intervalSec * 2.5 * 1000));
        } else {
          setPollStaleMs(POLL_STALE_MS[timeframe] ?? DEFAULT_POLL_STALE_MS);
        }
      } catch {
        if (!cancelled) setServerError('Live status unavailable');
      }
    };

    poll();
    const id = window.setInterval(poll, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [instrument, timeframe, applyDataPoint]);

  useEffect(() => {
    const id = window.setInterval(() => setTick((t) => t + 1), 3000);
    return () => window.clearInterval(id);
  }, []);

  const tfSec = TIMEFRAME_SEC[timeframe] ?? 3600;
  const dataStaleMs = tfSec * 2.5 * 1000;
  const dataFresh =
    lastUpdate !== null && Date.now() - lastUpdate.getTime() <= dataStaleMs;

  const warmingUp =
    schedulerRunning &&
    focusedMatches &&
    !hasPairPoll &&
    !dataFresh &&
    Date.now() - focusStartedAt < WARMING_UP_MS;

  const pollFresh =
    warmingUp ||
    (lastPollAt !== null && Date.now() - lastPollAt.getTime() <= pollStaleMs);

  const feedOffline =
    wsConnected &&
    !replayBlocked &&
    !serverError &&
    !warmingUp &&
    !dataFresh &&
    !pollFresh;

  void tick;

  return {
    lastUpdate,
    lastPollAt,
    source,
    close,
    serverError,
    replayBlocked,
    dataFresh,
    pollFresh,
    warmingUp,
    feedOffline,
  };
}