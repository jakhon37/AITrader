/** Minimum stop distance as % of entry — floor per timeframe so lines are visible on chart. */
/** Minimum price-axis span when framing order lines (prevents over-zoom). */
export const TIMEFRAME_VIEW_MIN_PCT: Record<string, number> = {
  '1m': 0.008,
  '5m': 0.01,
  '15m': 0.012,
  '30m': 0.014,
  '1h': 0.018,
  '4h': 0.025,
  '1d': 0.04,
  '1w': 0.07,
};

const TIMEFRAME_SL_FLOOR_PCT: Record<string, number> = {
  '1m': 0.0015,
  '5m': 0.0025,
  '15m': 0.004,
  '30m': 0.005,
  '1h': 0.008,
  '4h': 0.015,
  '1d': 0.03,
  '1w': 0.06,
};

export interface BarRange {
  high: number;
  low: number;
}

const RR_RATIO = 3;

function averageBarRange(bars: BarRange[]): number {
  if (bars.length === 0) return 0;
  const ranges = bars.map((b) => Math.max(0, b.high - b.low));
  return ranges.reduce((sum, r) => sum + r, 0) / ranges.length;
}

export function getOrderLevelDefaults(
  timeframe: string,
  side: 'buy' | 'sell',
  entry: number,
  recentBars: BarRange[] = [],
): { sl: number; tp: number; slDistance: number } {
  if (entry <= 0) {
    return { sl: 0, tp: 0, slDistance: 0 };
  }

  const floorPct = TIMEFRAME_SL_FLOOR_PCT[timeframe] ?? 0.008;
  let slDistance = entry * floorPct;

  if (recentBars.length >= 5) {
    const avgRange = averageBarRange(recentBars.slice(-30));
    // ~2× recent average candle range, scaled up slightly on higher timeframes
    const rangeMultiplier = timeframe === '1d' || timeframe === '1w' ? 2.5 : 2.0;
    slDistance = Math.max(slDistance, avgRange * rangeMultiplier);
  }

  const tpDistance = slDistance * RR_RATIO;

  return {
    slDistance,
    sl: side === 'buy' ? entry - slDistance : entry + slDistance,
    tp: side === 'buy' ? entry + tpDistance : entry - tpDistance,
  };
}

export function getTakeProfitFromStop(
  side: 'buy' | 'sell',
  entry: number,
  sl: number,
): number {
  const slDistance = Math.abs(entry - sl);
  return side === 'buy' ? entry + slDistance * RR_RATIO : entry - slDistance * RR_RATIO;
}

export function getStopFromTakeProfit(
  side: 'buy' | 'sell',
  entry: number,
  tp: number,
): number {
  const tpDistance = Math.abs(tp - entry);
  const slDistance = tpDistance / RR_RATIO;
  return side === 'buy' ? entry - slDistance : entry + slDistance;
}