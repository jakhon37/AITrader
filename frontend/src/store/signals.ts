import { create } from 'zustand';
import type { ChartMarker, TradeSignal, FundamentalSignal, TechnicalSignal } from '../types';

interface HealthDiv { status: string; division: string; message?: string; }
interface HealthStatus { status: string; divisions: Record<string, HealthDiv>; }

interface SignalsStore {
  tradeSignals: TradeSignal[];
  tradeByInstrument: Record<string, TradeSignal>;
  chartMarkers: ChartMarker[];
  fundamentalSignals: FundamentalSignal[];
  fundamentalByInstrument: Record<string, FundamentalSignal>;
  technicalByInstrument: Record<string, TechnicalSignal>;
  healthStatus: HealthStatus;
  wsConnected: boolean;
  addTradeSignal: (s: TradeSignal) => void;
  addChartMarker: (m: ChartMarker) => void;
  addFundamentalSignal: (s: FundamentalSignal) => void;
  setTechnicalSignal: (s: TechnicalSignal) => void;
  setHealthDiv: (div: HealthDiv) => void;
  initTradeSignals: (signals: TradeSignal[]) => void;
  initChartMarkers: (markers: ChartMarker[]) => void;
  initFundamentalSignals: (signals: FundamentalSignal[]) => void;
  setWsConnected: (connected: boolean) => void;
}

function instrumentKey(value: string | { value?: string } | undefined): string {
  if (!value) return '';
  if (typeof value === 'string') return value.toUpperCase();
  return String(value.value ?? '').toUpperCase();
}

const MAX_SIGNALS = 50;
const MAX_CHART_MARKERS = 200;

function dedupeByMarkerId<T extends { marker_id?: string }>(items: T[]): T[] {
  const seen = new Set<string>();
  const out: T[] = [];
  for (const item of items) {
    const id = item.marker_id;
    if (!id) {
      out.push(item);
      continue;
    }
    if (seen.has(id)) continue;
    seen.add(id);
    out.push(item);
  }
  return out;
}

/** Keep alternating LONG/SHORT markers; drop neutral and same-direction neighbours. */
export function normalizeChartMarkers(markers: ChartMarker[]): ChartMarker[] {
  const sorted = [...markers].sort(
    (a, b) => new Date(a.bar_time).getTime() - new Date(b.bar_time).getTime(),
  );
  const out: ChartMarker[] = [];
  for (const m of sorted) {
    const dir = m.direction?.toLowerCase();
    if (dir !== 'long' && dir !== 'short') continue;
    const last = out[out.length - 1];
    if (last && last.direction === m.direction) continue;
    const barKey = Math.floor(new Date(m.bar_time).getTime() / 1000);
    if (last && Math.floor(new Date(last.bar_time).getTime() / 1000) === barKey) continue;
    out.push(m);
  }
  return out.slice(-MAX_CHART_MARKERS);
}

function dedupeBySignalId<T extends { signal_id?: string }>(items: T[]): T[] {
  const seen = new Set<string>();
  const out: T[] = [];
  for (const item of items) {
    const id = item.signal_id;
    if (!id) {
      out.push(item);
      continue;
    }
    if (seen.has(id)) continue;
    seen.add(id);
    out.push(item);
  }
  return out;
}

function prependUnique<T extends { signal_id?: string }>(items: T[], incoming: T): T[] {
  if (!incoming.signal_id) {
    return [incoming, ...items].slice(0, MAX_SIGNALS);
  }
  const without = items.filter((x) => x.signal_id !== incoming.signal_id);
  return [incoming, ...without].slice(0, MAX_SIGNALS);
}

function latestByInstrument<T extends { instrument: string | { value?: string } }>(
  signals: T[],
): Record<string, T> {
  const map: Record<string, T> = {};
  for (const sig of [...signals].reverse()) {
    const key = instrumentKey(sig.instrument as string | { value?: string });
    if (key) {
      map[key] = sig;
    }
  }
  return map;
}

export const useSignalsStore = create<SignalsStore>((set) => ({
  tradeSignals: [],
  tradeByInstrument: {},
  chartMarkers: [],
  fundamentalSignals: [],
  fundamentalByInstrument: {},
  technicalByInstrument: {},
  healthStatus: { status: 'ok', divisions: {} },
  wsConnected: false,
  addTradeSignal: (s) =>
    set((state) => {
      const key = instrumentKey(s.instrument as string | { value?: string });
      return {
        tradeSignals: prependUnique(state.tradeSignals, s),
        tradeByInstrument: key
          ? { ...state.tradeByInstrument, [key]: s }
          : state.tradeByInstrument,
      };
    }),
  addChartMarker: (m) =>
    set((state) => {
      const merged = normalizeChartMarkers([...state.chartMarkers, m]);
      return { chartMarkers: merged };
    }),
  addFundamentalSignal: (s) =>
    set((state) => {
      const key = instrumentKey(s.instrument as string | { value?: string });
      return {
        fundamentalSignals: prependUnique(state.fundamentalSignals, s),
        fundamentalByInstrument: key
          ? { ...state.fundamentalByInstrument, [key]: s }
          : state.fundamentalByInstrument,
      };
    }),
  setTechnicalSignal: (s) =>
    set((state) => {
      const key = instrumentKey(s.instrument as string | { value?: string });
      if (!key) return state;
      return {
        technicalByInstrument: { ...state.technicalByInstrument, [key]: s },
      };
    }),
  setHealthDiv: (div) => set((state) => {
    const divisions = { ...state.healthStatus.divisions, [div.division]: div };
    let status = 'ok';
    for (const d of Object.values(divisions)) {
      if (d.status === 'down') { status = 'down'; break; }
      if (d.status === 'degraded') status = 'degraded';
    }
    return { healthStatus: { status, divisions } };
  }),
  initTradeSignals: (signals) => {
    const tradeSignals = dedupeBySignalId(signals).slice(0, MAX_SIGNALS);
    set({ tradeSignals, tradeByInstrument: latestByInstrument(tradeSignals) });
  },
  initChartMarkers: (markers) => {
    const chartMarkers = normalizeChartMarkers(dedupeByMarkerId(markers));
    set({ chartMarkers });
  },
  initFundamentalSignals: (signals) => {
    const fundamentalSignals = dedupeBySignalId(signals).slice(0, MAX_SIGNALS);
    set({
      fundamentalSignals,
      fundamentalByInstrument: latestByInstrument(fundamentalSignals),
    });
  },
  setWsConnected: (connected) => set({ wsConnected: connected }),
}));
