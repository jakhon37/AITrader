/**
 * Client-side session filter (defense in depth — API also filters via instruments.yaml).
 * Rules mirror config/instruments.yaml session_hours / daily_break; gold uses XAUUSD block.
 */
/** FX session hours in UTC — matches config/instruments.yaml (Sun 22:00 → Fri 22:00). */
export const FX_SESSION_UTC = {
  open: '22:00',
  close: '22:00',
} as const;

/**
 * Gold session (Dukascopy): Sun 22:00 UTC open, daily close 21:00 UTC,
 * 1h maintenance break 21:00–22:00 UTC, weekly close Fri 21:00 → Sun 22:00.
 */
export const GOLD_SESSION_UTC = {
  open: '22:00',
  close: '21:00',
  dailyBreakStart: '21:00',
  dailyBreakEnd: '22:00',
} as const;

const PIP_SIZE: Record<string, number> = {
  XAUUSD: 0.01,
  USDJPY: 0.01,
  EURUSD: 0.0001,
  GBPUSD: 0.0001,
};

/** True when the bar timestamp falls inside the standard FX trading week (UTC). */
export function isFxSessionBar(unixSec: number): boolean {
  const dt = new Date(unixSec * 1000);
  const day = dt.getUTCDay();
  const hour = dt.getUTCHours();

  if (day === 6) return false;
  if (day === 5 && hour >= 22) return false;
  if (day === 0 && hour < 22) return false;

  return true;
}

/** True when the bar falls inside the Dukascopy gold trading window (UTC). */
export function isGoldSessionBar(unixSec: number): boolean {
  const dt = new Date(unixSec * 1000);
  const day = dt.getUTCDay();
  const hour = dt.getUTCHours();

  if (day === 6) return false;
  if (day === 0 && hour < 22) return false;
  if (hour === 21) return false;
  if (day === 5 && hour >= 21) return false;

  return true;
}

export function isInstrumentSessionBar(unixSec: number, instrument?: string): boolean {
  if (instrument?.toUpperCase() === 'XAUUSD') {
    return isGoldSessionBar(unixSec);
  }
  return isFxSessionBar(unixSec);
}

/** Stale flat bars left by feeds during market pauses (weekends, daily gold break). */
export function isInactiveFlatBar(
  bar: { open: number; high: number; low: number; close: number; volume?: number },
  instrument?: string,
): boolean {
  const vol = bar.volume ?? 0;
  const range = bar.high - bar.low;
  const pip = PIP_SIZE[instrument?.toUpperCase() ?? ''] ?? 0.0001;
  if (range <= 0) return true;
  if (vol <= 0 && range <= pip * 2) return true;
  if (bar.open === bar.close && range <= pip) return true;
  return false;
}