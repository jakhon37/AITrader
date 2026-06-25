const API_BASE = import.meta.env.VITE_API_BASE ?? '/api';

export async function getOHLCV(
  instrument: string,
  timeframe: string,
  start: string,
  end: string,
  options?: { focus?: boolean },
) {
  const params = new URLSearchParams({ instrument, timeframe, start, end });
  if (options?.focus) params.set('focus', 'true');
  const res = await fetch(`${API_BASE}/data/ohlcv?${params.toString()}`);
  if (!res.ok) throw new Error('Failed to fetch OHLCV');
  return res.json();
}

/** Register scheduler focus once per instrument/timeframe change (not per chart page). */
export async function focusChartPair(instrument: string, timeframe: string) {
  const params = new URLSearchParams({ instrument, timeframe });
  const res = await fetch(`${API_BASE}/data/focus?${params.toString()}`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to focus chart pair');
  return res.json();
}

export async function getLiveStatus() {
  const res = await fetch(`${API_BASE}/data/live-status`);
  if (!res.ok) throw new Error('Failed to fetch live status');
  return res.json();
}

export interface DataInstrumentConfig {
  enabled: boolean;
  pip_size: number;
  session_hours: { open: string; close: string };
  daily_break: { start: string; end: string } | null;
  primary_timeframe: string;
}

export interface DataInstrumentsResponse {
  enabled: string[];
  supported: string[];
  configs: Record<string, DataInstrumentConfig>;
}

export async function getDataInstruments(): Promise<DataInstrumentsResponse> {
  const res = await fetch(`${API_BASE}/data/instruments`);
  if (!res.ok) throw new Error('Failed to fetch instruments');
  return res.json();
}

export async function releaseReplaySession() {
  const res = await fetch(`${API_BASE}/replay/release`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to release replay session');
  return res.json();
}

export async function getTradeSignals() {
  const res = await fetch(`${API_BASE}/signals/trade`);
  if (!res.ok) throw new Error('Failed to fetch trade signals');
  return res.json();
}

export async function getLatestSignals(instrument: string) {
  const params = new URLSearchParams({ instrument });
  const res = await fetch(`${API_BASE}/signals/latest?${params.toString()}`);
  if (!res.ok) throw new Error('Failed to fetch latest signals');
  return res.json();
}

export async function getFundamentalSignals() {
  const res = await fetch(`${API_BASE}/signals/fundamental`);
  if (!res.ok) throw new Error('Failed to fetch fundamental signals');
  return res.json();
}

export async function getUpcomingCalendar(hours = 48, minImpact: 'low' | 'medium' | 'high' = 'low') {
  const params = new URLSearchParams({
    hours: String(hours),
    min_impact: minImpact,
  });
  const res = await fetch(`${API_BASE}/data/calendar/upcoming?${params.toString()}`);
  if (!res.ok) throw new Error('Failed to fetch upcoming calendar');
  return res.json();
}

export async function getPortfolio() {
  const res = await fetch(`${API_BASE}/portfolio/state`);
  if (!res.ok) throw new Error('Failed to fetch portfolio');
  return res.json();
}

export async function getHealth() {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error('Failed to fetch health');
  return res.json();
}

export async function getInstrumentConfig(instrument: string) {
  const res = await fetch(`${API_BASE}/config/${instrument}`);
  if (!res.ok) throw new Error('Failed to fetch config');
  return res.json();
}

export async function putInstrumentConfig(instrument: string, config: object) {
  const res = await fetch(`${API_BASE}/config/${instrument}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to save config');
  }
  return res.json();
}

export async function startReplay(payload: { instrument: string; start_date: string; end_date?: string; initial_capital: number; mode: string; speed: number; timeframe?: string; calculate_indicators?: boolean }) {
  const res = await fetch(`${API_BASE}/replay/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error('Failed to start replay');
  return res.json();
}

export async function changeReplayIndicators(enabled: boolean) {
  const res = await fetch(`${API_BASE}/replay/indicators`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled }),
  });
  if (!res.ok) throw new Error('Failed to update indicators status');
  return res.json();
}

export async function pauseReplay() {
  const res = await fetch(`${API_BASE}/replay/pause`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to pause replay');
  return res.json();
}

export async function resumeReplay() {
  const res = await fetch(`${API_BASE}/replay/resume`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to resume replay');
  return res.json();
}

export async function stepReplay() {
  const res = await fetch(`${API_BASE}/replay/step`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to step replay');
  return res.json();
}

export async function placeManualOrder(
  side: string,
  size: number,
  entryPrice?: number | null,
  stopLoss?: number | null,
  takeProfit?: number | null
) {
  const res = await fetch(`${API_BASE}/replay/order`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      side,
      size,
      entry_price: entryPrice,
      stop_loss: stopLoss,
      take_profit: takeProfit,
    }),
  });
  if (!res.ok) throw new Error('Failed to place manual order');
  return res.json();
}

export async function cancelPendingOrder(orderId: string) {
  const res = await fetch(`${API_BASE}/replay/order/cancel`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ order_id: orderId }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to cancel pending order');
  }
  return res.json();
}

export async function modifyPendingOrder(
  orderId: string,
  side: string,
  size: number,
  entryPrice: number,
  stopLoss?: number | null,
  takeProfit?: number | null,
) {
  const res = await fetch(`${API_BASE}/replay/order/modify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      order_id: orderId,
      side,
      size,
      entry_price: entryPrice,
      stop_loss: stopLoss,
      take_profit: takeProfit,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to modify pending order');
  }
  return res.json();
}

export async function closeManualPosition(instrument: string) {
  const res = await fetch(`${API_BASE}/replay/close`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ instrument }),
  });
  if (!res.ok) throw new Error('Failed to close position');
  return res.json();
}

export async function closePositionLeg(legId: string) {
  const res = await fetch(`${API_BASE}/replay/close`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ leg_id: legId }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to close position leg');
  }
  return res.json();
}

export async function modifyOpenPosition(
  legId: string,
  stopLoss?: number | null,
  takeProfit?: number | null,
  options?: { clearSl?: boolean; clearTp?: boolean },
) {
  const res = await fetch(`${API_BASE}/replay/position/modify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      leg_id: legId,
      stop_loss: stopLoss ?? null,
      take_profit: takeProfit ?? null,
      clear_sl: options?.clearSl ?? false,
      clear_tp: options?.clearTp ?? false,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to update position');
  }
  return res.json();
}

export async function stopReplay() {
  const res = await fetch(`${API_BASE}/replay/stop`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to stop replay');
  return res.json();
}

export async function getReplayState() {
  const res = await fetch(`${API_BASE}/replay/state`);
  if (!res.ok) throw new Error('Failed to fetch replay state');
  return res.json();
}

export async function getSessionAnalytics() {
  const res = await fetch(`${API_BASE}/replay/analytics`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to fetch session analytics');
  }
  return res.json();
}

export async function changeReplayTimeframe(timeframe: string) {
  const res = await fetch(`${API_BASE}/replay/timeframe`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ timeframe }),
  });
  if (!res.ok) throw new Error('Failed to change replay timeframe');
  return res.json();
}

export async function changeReplaySpeed(speed: number) {
  const res = await fetch(`${API_BASE}/replay/speed`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ speed }),
  });
  if (!res.ok) throw new Error('Failed to change replay speed');
  return res.json();
}
