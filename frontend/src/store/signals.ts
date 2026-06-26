import { create } from 'zustand';
import type { TradeSignal, FundamentalSignal, TechnicalSignal } from '../types';

interface HealthDiv { status: string; division: string; message?: string; }
interface HealthStatus { status: string; divisions: Record<string, HealthDiv>; }

interface SignalsStore {
  tradeSignals: TradeSignal[];
  tradeByInstrument: Record<string, TradeSignal>;
  fundamentalSignals: FundamentalSignal[];
  fundamentalByInstrument: Record<string, FundamentalSignal>;
  technicalByInstrument: Record<string, TechnicalSignal>;
  healthStatus: HealthStatus;
  wsConnected: boolean;
  addTradeSignal: (s: TradeSignal) => void;
  addFundamentalSignal: (s: FundamentalSignal) => void;
  setTechnicalSignal: (s: TechnicalSignal) => void;
  setHealthDiv: (div: HealthDiv) => void;
  initTradeSignals: (signals: TradeSignal[]) => void;
  initFundamentalSignals: (signals: FundamentalSignal[]) => void;
  setWsConnected: (connected: boolean) => void;
}

function instrumentKey(value: string | { value?: string } | undefined): string {
  if (!value) return '';
  if (typeof value === 'string') return value.toUpperCase();
  return String(value.value ?? '').toUpperCase();
}

const MAX_SIGNALS = 50;

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
  initFundamentalSignals: (signals) => {
    const fundamentalSignals = dedupeBySignalId(signals).slice(0, MAX_SIGNALS);
    set({
      fundamentalSignals,
      fundamentalByInstrument: latestByInstrument(fundamentalSignals),
    });
  },
  setWsConnected: (connected) => set({ wsConnected: connected }),
}));
