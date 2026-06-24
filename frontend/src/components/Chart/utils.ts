import type { IChartApi, ISeriesApi } from 'lightweight-charts';

export const LOOKBACK: Record<string, number> = {
  '1m': 2, '5m': 5, '15m': 10, '30m': 20, '1h': 40, '4h': 180, '1d': 1000, '1w': 7000,
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

export const PAGINATION_LOOKBACK: Record<string, number> = {
  '1m': 2,
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
export function ensureOrderLinesInView(
  candleSeries: ISeriesApi<'Candlestick'>,
  prices: (number | null | undefined)[],
  context?: OrderLinesViewContext,
): void {
  const active = prices.filter((p): p is number => p != null && p > 0);
  if (active.length < 2) return;

  const scale = candleSeries.priceScale();
  scale.setAutoScale(true);
  const current = scale.getVisibleRange();
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
    scale.setAutoScale(false);
    scale.setVisibleRange({ from: center - span / 2, to: center + span / 2 });
    return;
  }

  scale.setAutoScale(false);
  scale.setVisibleRange({ from: unionMin, to: unionMax });
}

export function resetPriceScaleAuto(candleSeries: ISeriesApi<'Candlestick'>): void {
  candleSeries.priceScale().setAutoScale(true);
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

export const isTradingBar = (bar: { time: number; open: number; close: number; volume?: number }): boolean => {
  const dt = new Date(bar.time * 1000);
  const day = dt.getUTCDay();
  const hour = dt.getUTCHours();

  if (day === 6) return false;
  if (day === 5 && hour >= 22) return false;
  if (day === 0 && hour < 22) return false;

  if (bar.volume !== undefined && bar.volume === 0 && bar.open === bar.close) {
    return false;
  }

  return true;
};
