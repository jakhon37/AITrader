import type { IChartApi, ISeriesApi } from 'lightweight-charts';
import { isInactiveFlatBar, isInstrumentSessionBar } from '../../utils/fxSession';

export const LOOKBACK: Record<string, number> = {
  // 1m: yfinance max window is 7 days — load full week for continuity
  '1m': 7, '5m': 7, '15m': 14, '30m': 20, '1h': 40, '4h': 180, '1d': 1000, '1w': 7000,
};

/** Default number of candles to show when auto-fitting the viewport. */
export const VISIBLE_BARS: Record<string, number> = {
  '1m': 150,
  '5m': 150,
  '15m': 120,
  '30m': 100,
  '1h': 96,
  '4h': 80,
  '1d': 60,
  '1w': 52,
};

export type ChartViewportMode = 'auto' | 'fit-all';

export const MAX_BUFFER = 20000;

export const TIMEFRAME_SECONDS: Record<string, number> = {
  '1m': 60,
  '5m': 300,
  '15m': 900,
  '30m': 1800,
  '1h': 3600,
  '4h': 14400,
  '1d': 86400,
  '1w': 604800,
};

/** Seconds per bar — uses the last gap in loaded data, falls back to nominal timeframe. */
export function getBarStep(barTimes: readonly number[], timeframe: string): number {
  if (barTimes.length >= 2) {
    return barTimes[barTimes.length - 1] - barTimes[barTimes.length - 2];
  }
  return TIMEFRAME_SECONDS[timeframe] ?? 3600;
}

/** Map a stored drawing timestamp to a chart logical index (supports future extrapolation). */
export function drawingTimeToLogical(
  time: number,
  barTimes: readonly number[],
  timeframe: string,
): number {
  if (barTimes.length === 0) return 0;
  const lastIdx = barTimes.length - 1;
  const step = getBarStep(barTimes, timeframe);
  if (time > barTimes[lastIdx] + step * 0.5) {
    return lastIdx + (time - barTimes[lastIdx]) / step;
  }
  if (time < barTimes[0] - step * 0.5) {
    return (time - barTimes[0]) / step;
  }
  return findClosestBarIndex(barTimes, time);
}

/** Map a chart logical index to a drawing timestamp (snaps history, extrapolates future). */
export function logicalToDrawingTime(
  logical: number,
  barTimes: readonly number[],
  timeframe: string,
): number {
  if (barTimes.length === 0) return 0;
  const lastIdx = barTimes.length - 1;
  const step = getBarStep(barTimes, timeframe);
  if (logical > lastIdx + 0.5) {
    return barTimes[lastIdx] + (logical - lastIdx) * step;
  }
  if (logical < -0.5) {
    return barTimes[0] + logical * step;
  }
  const idx = Math.max(0, Math.min(lastIdx, Math.round(logical)));
  return barTimes[idx];
}

export const PAGINATION_LOOKBACK: Record<string, number> = {
  '1m': 7,
  '5m': 7,
  '15m': 20,
  '30m': 40,
  '1h': 80,
  '4h': 300,
  '1d': 1000,
  '1w': 5000,
};

export interface OrderLinesViewContext {
  candleLow?: number;
  candleHigh?: number;
  entry?: number;
  /** Minimum total span as % of entry — prevents over-zoom when lines are close together. */
  minSpanPct?: number;
}

/**
 * One-shot view adjust when SL/TP are first placed.
 * Only zooms OUT if lines fall outside the current range — never zooms IN.
 * Caller must invoke only on focus-key bump, not while dragging lines.
 */
function safePriceScaleOp(fn: () => void): void {
  try {
    fn();
  } catch {
    // Chart or series may be disposed during rapid layout / session updates.
  }
}

export function ensureOrderLinesInView(
  candleSeries: ISeriesApi<'Candlestick'>,
  prices: (number | null | undefined)[],
  context?: OrderLinesViewContext,
): void {
  const active = prices.filter((p): p is number => p != null && p > 0);
  if (active.length < 2) return;

  let scale;
  let current;
  try {
    scale = candleSeries.priceScale();
    safePriceScaleOp(() => scale.setAutoScale(true));
    current = scale.getVisibleRange();
  } catch {
    return;
  }
  if (!current) return;

  const orderMin = Math.min(...active);
  const orderMax = Math.max(...active);
  const entry = context?.entry && context.entry > 0
    ? context.entry
    : (orderMin + orderMax) / 2;

  const currentSpan = current.to - current.from;
  const minSpanPct = context?.minSpanPct ?? 0.012;
  const minSpan = Math.max(currentSpan, entry * minSpanPct);
  const pad = minSpan * 0.08;

  const linesFit =
    orderMin >= current.from + pad &&
    orderMax <= current.to - pad;

  if (linesFit) return;

  const unionMin = Math.min(current.from, orderMin - pad);
  const unionMax = Math.max(current.to, orderMax + pad);
  let span = unionMax - unionMin;
  if (span < minSpan) {
    const center = (orderMin + orderMax) / 2;
    span = minSpan;
    safePriceScaleOp(() => {
      scale.setAutoScale(false);
      scale.setVisibleRange({ from: center - span / 2, to: center + span / 2 });
    });
    return;
  }

  safePriceScaleOp(() => {
    scale.setAutoScale(false);
    scale.setVisibleRange({ from: unionMin, to: unionMax });
  });
}

export function resetPriceScaleAuto(candleSeries: ISeriesApi<'Candlestick'>): void {
  safePriceScaleOp(() => candleSeries.priceScale().setAutoScale(true));
}

/** Lock the current Y-axis range so drawing tools don't fight auto-scale. */
export function freezePriceScale(candleSeries: ISeriesApi<'Candlestick'>): void {
  safePriceScaleOp(() => {
    const scale = candleSeries.priceScale();
    const range = scale.getVisibleRange();
    scale.setAutoScale(false);
    if (range) {
      scale.setVisibleRange(range);
    }
  });
}

export function unfreezePriceScale(candleSeries: ISeriesApi<'Candlestick'>): void {
  resetPriceScaleAuto(candleSeries);
}

export function applyChartViewport(
  chart: IChartApi,
  data: { time: number }[],
  timeframe: string,
  options?: { anchorTime?: number; mode?: ChartViewportMode },
): void {
  if (data.length === 0) return;

  const mode = options?.mode ?? 'auto';
  if (mode === 'fit-all') {
    chart.timeScale().fitContent();
    return;
  }

  const visibleBars = VISIBLE_BARS[timeframe] ?? 100;
  let anchorIndex = data.length - 1;
  if (options?.anchorTime !== undefined) {
    const idx = findClosestIndex(data, options.anchorTime);
    if (idx !== -1) anchorIndex = idx;
  }

  const from = Math.max(0, anchorIndex - visibleBars + 1);
  const rightPadding = Math.min(12, Math.max(3, Math.floor(visibleBars * 0.08)));
  chart.timeScale().setVisibleLogicalRange({
    from,
    to: anchorIndex + rightPadding,
  });
}

export const findClosestIndex = (data: { time: number }[], targetTime: number): number => {
  if (data.length === 0) return -1;
  let closestIdx = 0;
  let minDiff = Math.abs(data[0].time - targetTime);
  for (let i = 1; i < data.length; i++) {
    const diff = Math.abs(data[i].time - targetTime);
    if (diff < minDiff) {
      minDiff = diff;
      closestIdx = i;
    }
  }
  return closestIdx;
};

/** Nearest bar index for a unix timestamp against sorted bar times. */
export const findClosestBarIndex = (barTimes: readonly number[], targetTime: number): number => {
  if (barTimes.length === 0) return -1;
  if (targetTime <= barTimes[0]) return 0;
  if (targetTime >= barTimes[barTimes.length - 1]) return barTimes.length - 1;

  let lo = 0;
  let hi = barTimes.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (barTimes[mid] === targetTime) return mid;
    if (barTimes[mid] < targetTime) lo = mid + 1;
    else hi = mid - 1;
  }

  if (lo <= 0) return 0;
  if (lo >= barTimes.length) return barTimes.length - 1;
  const diffLo = Math.abs(barTimes[lo] - targetTime);
  const diffHi = Math.abs(barTimes[lo - 1] - targetTime);
  return diffLo < diffHi ? lo : lo - 1;
};

export const timeAtBarIndex = (barTimes: readonly number[], index: number): number => {
  if (barTimes.length === 0) return 0;
  const clamped = Math.max(0, Math.min(barTimes.length - 1, index));
  return barTimes[clamped];
};

export const snapTimeToBar = (barTimes: readonly number[], time: number): number => {
  const idx = findClosestBarIndex(barTimes, time);
  return idx === -1 ? time : barTimes[idx];
};

export type TradingBarOptions = {
  /** Allow zero-volume flat bars (common for forex live feeds). */
  allowZeroVolume?: boolean;
};

/** Minimal OHLCV validation for live terminal charts — keeps all API bars. */
export const isValidChartBar = (bar: {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
}): boolean => {
  const t = typeof bar.time === 'number' ? bar.time : Number(bar.time);
  if (!Number.isFinite(t) || t <= 0) return false;
  return [bar.open, bar.high, bar.low, bar.close].every((v) => Number.isFinite(Number(v)));
};

export type ChartBarFilterOptions = {
  replayMode?: boolean;
  instrument?: string;
};

export function filterChartBars(
  data: { time: number; open: number; high: number; low: number; close: number; volume?: number }[],
  options?: ChartBarFilterOptions,
): typeof data {
  if (!Array.isArray(data)) return [];
  const instrument = options?.instrument;
  return data.filter(
    (bar) => isValidChartBar(bar) && isTradingBar(bar, { instrument }),
  );
}

export const isTradingBar = (
  bar: { time: number; open: number; high: number; low: number; close: number; volume?: number },
  options?: TradingBarOptions & { instrument?: string },
): boolean => {
  const t = typeof bar.time === 'number' ? bar.time : Number(bar.time);
  const instrument = options?.instrument;
  if (!Number.isFinite(t) || !isInstrumentSessionBar(t, instrument)) return false;
  if (isInactiveFlatBar(bar, instrument)) return false;
  return true;
};
