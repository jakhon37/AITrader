import { create } from 'zustand';
import type { TradeSignal, FundamentalSignal, TechnicalSignal } from '../types';

interface HealthDiv { status: string; division: string; message?: string; }
interface HealthStatus { status: string; divisions: Record<string, HealthDiv>; }

interface SignalsStore {
  tradeSignals: TradeSignal[];
  fundamentalSignals: FundamentalSignal[];
  technicalSignal: TechnicalSignal | null;
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

export const useSignalsStore = create<SignalsStore>((set) => ({
  tradeSignals: [],
  fundamentalSignals: [],
  technicalSignal: null,
  healthStatus: { status: 'ok', divisions: {} },
  wsConnected: false,
  addTradeSignal: (s) => set((state) => ({ tradeSignals: [s, ...state.tradeSignals.slice(0, 49)] })),
  addFundamentalSignal: (s) => set((state) => ({ fundamentalSignals: [s, ...state.fundamentalSignals.slice(0, 49)] })),
  setTechnicalSignal: (s) => set({ technicalSignal: s }),
  setHealthDiv: (div) => set((state) => {
    const divisions = { ...state.healthStatus.divisions, [div.division]: div };
    let status = 'ok';
    for (const d of Object.values(divisions)) {
      if (d.status === 'down') { status = 'down'; break; }
      if (d.status === 'degraded') status = 'degraded';
    }
    return { healthStatus: { status, divisions } };
  }),
  initTradeSignals: (signals) => set({ tradeSignals: signals.slice(0, 50) }),
  initFundamentalSignals: (signals) => set({ fundamentalSignals: signals.slice(0, 50) }),
  setWsConnected: (connected) => set({ wsConnected: connected }),
}));
