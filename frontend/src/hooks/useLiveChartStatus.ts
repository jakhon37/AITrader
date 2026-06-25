import { useEffect, useState } from 'react';
import { getLiveStatus } from '../api/client';

/** Max age before we treat the focused pair poll as stale (scaled per timeframe). */
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

export type LiveChartStatus = {
  lastUpdate: Date | null;
  lastPollAt: Date | null;
  source: string | null;
  close: number | null;
  serverError: string | null;
  replayBlocked: boolean;
  stale: boolean;
  barStale: boolean;
};

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
  const [tick, setTick] = useState(0);

  useEffect(() => {
    setLastUpdate(null);
    setLastPollAt(null);
    setClose(null);
    setServerError(null);
  }, [instrument, timeframe]);

  useEffect(() => {
    const handleBar = (e: Event) => {
      const customEvent = e as CustomEvent<{
        instrument: string;
        timeframe: string;
        source?: string;
        bar: { close: number };
      }>;
      const { instrument: barInst, timeframe: barTf, source: barSource, bar } = customEvent.detail;
      if (
        String(barInst).toUpperCase() === instrument.toUpperCase() &&
        String(barTf) === timeframe
      ) {
        setLastUpdate(new Date());
        setSource(barSource ?? 'dukascopy');
        setClose(bar.close);
        setServerError(null);
      }
    };

    window.addEventListener('ohlcv_bar', handleBar);
    return () => window.removeEventListener('ohlcv_bar', handleBar);
  }, [instrument, timeframe]);

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      try {
        const status = await getLiveStatus();
        if (cancelled) return;
        setReplayBlocked(Boolean(status.replay_active));
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
        const err = pair?.last_error ?? status.last_error ?? null;
        setServerError(err);
        if (pair?.source) setSource(pair.source);
        if (typeof pair?.close === 'number') setClose(pair.close);
        if (pair?.last_bar_at) setLastUpdate(new Date(pair.last_bar_at));
        if (pair?.last_poll_at) {
          setLastPollAt(new Date(pair.last_poll_at));
        } else if (status.last_poll_at) {
          setLastPollAt(new Date(status.last_poll_at));
        }

        const focused = status.focused_pair as
          | { instrument: string; timeframe: string }
          | null
          | undefined;
        const focusedMatches =
          focused &&
          focused.instrument.toUpperCase() === instrument.toUpperCase() &&
          focused.timeframe === timeframe;
        const intervalSec =
          typeof status.focused_poll_interval_sec === 'number'
            ? status.focused_poll_interval_sec
            : null;
        if (focusedMatches && intervalSec !== null && intervalSec > 0) {
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
  }, [instrument, timeframe]);

  useEffect(() => {
    const id = window.setInterval(() => setTick((t) => t + 1), 3000);
    return () => window.clearInterval(id);
  }, []);

  const barStaleMs = (POLL_STALE_MS[timeframe] ?? DEFAULT_POLL_STALE_MS) * 3;
  const pollFresh =
    lastPollAt !== null && Date.now() - lastPollAt.getTime() <= pollStaleMs;
  const barStale =
    !lastUpdate || Date.now() - lastUpdate.getTime() > barStaleMs;
  const stale = !wsConnected || !pollFresh;

  void tick;

  return {
    lastUpdate,
    lastPollAt,
    source,
    close,
    serverError,
    replayBlocked,
    stale,
    barStale,
  };
}