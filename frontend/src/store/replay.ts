import { create } from 'zustand';

export type ReplayStatus = 'idle' | 'paused' | 'running' | 'ended';

interface ReplayStore {
  isActive: boolean;
  status: ReplayStatus;
  instrument: string;
  timeframe: string;
  currentTime: string | null;
  setSession: (patch: Partial<Pick<ReplayStore, 'isActive' | 'status' | 'instrument' | 'timeframe' | 'currentTime'>>) => void;
  reset: () => void;
}

export const useReplayStore = create<ReplayStore>((set) => ({
  isActive: false,
  status: 'idle',
  instrument: 'EURUSD',
  timeframe: '1h',
  currentTime: null,
  setSession: (patch) => set((state) => ({ ...state, ...patch })),
  reset: () =>
    set({
      isActive: false,
      status: 'idle',
      instrument: 'EURUSD',
      timeframe: '1h',
      currentTime: null,
    }),
}));