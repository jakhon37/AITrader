/** Client-side RSI / MACD series for indicator subplots (mirrors backend formulas). */

export interface IndicatorBar {
  time: number;
  close: number;
}

export interface RsiPoint {
  time: number;
  value: number;
}

export interface MacdPoint {
  time: number;
  macd: number;
  signal: number;
  hist: number;
}

function ema(values: number[], span: number): number[] {
  const out = new Array<number>(values.length).fill(NaN);
  if (values.length === 0) return out;
  const alpha = 2 / (span + 1);
  let prev = values[0];
  out[0] = prev;
  for (let i = 1; i < values.length; i += 1) {
    prev = alpha * values[i] + (1 - alpha) * prev;
    out[i] = prev;
  }
  return out;
}

function rollingMean(values: number[], window: number): number[] {
  const out = new Array<number>(values.length).fill(NaN);
  for (let i = window - 1; i < values.length; i += 1) {
    let sum = 0;
    for (let j = i - window + 1; j <= i; j += 1) sum += values[j];
    out[i] = sum / window;
  }
  return out;
}

export function computeRsiSeries(bars: IndicatorBar[], period = 14): RsiPoint[] {
  if (bars.length < period + 1) return [];
  const closes = bars.map((b) => b.close);
  const gains = new Array<number>(closes.length).fill(0);
  const losses = new Array<number>(closes.length).fill(0);
  for (let i = 1; i < closes.length; i += 1) {
    const delta = closes[i] - closes[i - 1];
    gains[i] = delta > 0 ? delta : 0;
    losses[i] = delta < 0 ? -delta : 0;
  }
  const avgGain = rollingMean(gains, period);
  const avgLoss = rollingMean(losses, period);
  const points: RsiPoint[] = [];
  for (let i = period; i < bars.length; i += 1) {
    const loss = avgLoss[i];
    if (!Number.isFinite(avgGain[i]) || !Number.isFinite(loss)) continue;
    const rs = loss === 0 ? 100 : avgGain[i] / loss;
    const rsi = 100 - 100 / (1 + rs);
    if (!Number.isFinite(rsi)) continue;
    points.push({ time: bars[i].time, value: rsi });
  }
  return points;
}

export function computeMacdSeries(
  bars: IndicatorBar[],
  fast = 12,
  slow = 26,
  signalPeriod = 9,
): MacdPoint[] {
  if (bars.length < slow + signalPeriod) return [];
  const closes = bars.map((b) => b.close);
  const emaFast = ema(closes, fast);
  const emaSlow = ema(closes, slow);
  const macdLine = closes.map((_, i) => emaFast[i] - emaSlow[i]);
  const signalLine = ema(macdLine.map((v) => (Number.isFinite(v) ? v : 0)), signalPeriod);
  const points: MacdPoint[] = [];
  const start = slow + signalPeriod - 2;
  for (let i = Math.max(start, 0); i < bars.length; i += 1) {
    const macd = macdLine[i];
    const signal = signalLine[i];
    if (!Number.isFinite(macd) || !Number.isFinite(signal)) continue;
    points.push({
      time: bars[i].time,
      macd,
      signal,
      hist: macd - signal,
    });
  }
  return points;
}

export function latestRsi(points: RsiPoint[]): number | null {
  return points.length ? points[points.length - 1].value : null;
}

export function latestMacd(points: MacdPoint[]): MacdPoint | null {
  return points.length ? points[points.length - 1] : null;
}