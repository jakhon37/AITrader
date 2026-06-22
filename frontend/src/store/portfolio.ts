import { create } from 'zustand';
import type { PortfolioState } from '../types';

const DEFAULT_PORTFOLIO: PortfolioState = {
  balance: 100000,
  equity: 100000,
  margin_used: 0,
  free_margin: 100000,
  open_positions: [],
  realized_pnl_today: 0,
  drawdown_pct: 0,
};

interface PortfolioStore {
  portfolio: PortfolioState;
  setPortfolio: (p: PortfolioState) => void;
}

export const usePortfolioStore = create<PortfolioStore>((set) => ({
  portfolio: DEFAULT_PORTFOLIO,
  setPortfolio: (portfolio) => set({ portfolio }),
}));
