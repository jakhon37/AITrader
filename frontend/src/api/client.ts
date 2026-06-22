const API_BASE = 'http://localhost:8000/api';

export async function getOHLCV(instrument: string, timeframe: string, start: string, end: string) {
  const params = new URLSearchParams({ instrument, timeframe, start, end });
  const res = await fetch(`${API_BASE}/data/ohlcv?${params.toString()}`);
  if (!res.ok) throw new Error('Failed to fetch OHLCV');
  return res.json();
}

export async function getTradeSignals() {
  const res = await fetch(`${API_BASE}/signals/trade`);
  if (!res.ok) throw new Error('Failed to fetch trade signals');
  return res.json();
}

export async function getFundamentalSignals() {
  const res = await fetch(`${API_BASE}/signals/fundamental`);
  if (!res.ok) throw new Error('Failed to fetch fundamental signals');
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
  if (!res.ok) throw new Error('Failed to save config');
  return res.json();
}

export async function startReplay(payload: { instrument: string; start_date: string; end_date: string; initial_capital: number; mode: string; speed: number; timeframe?: string }) {
  const res = await fetch(`${API_BASE}/replay/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error('Failed to start replay');
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

export async function placeManualOrder(side: string, size: number) {
  const res = await fetch(`${API_BASE}/replay/order`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ side, size }),
  });
  if (!res.ok) throw new Error('Failed to place manual order');
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

export async function changeReplayTimeframe(timeframe: string) {
  const res = await fetch(`${API_BASE}/replay/timeframe`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ timeframe }),
  });
  if (!res.ok) throw new Error('Failed to change replay timeframe');
  return res.json();
}
