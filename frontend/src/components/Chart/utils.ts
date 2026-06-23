
export const LOOKBACK: Record<string, number> = {
  '1m': 2, '5m': 5, '15m': 10, '30m': 20, '1h': 40, '4h': 180, '1d': 1000, '1w': 7000,
};

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
