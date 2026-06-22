import { useEffect } from 'react';
import { usePortfolioStore } from '../store/portfolio';
import { getPortfolio } from '../api/client';
import type { PortfolioState } from '../types';

export function usePortfolio(intervalMs = 5000) {
  const setPortfolio = usePortfolioStore((s) => s.setPortfolio);

  useEffect(() => {
    const poll = () => {
      getPortfolio()
        .then((data: PortfolioState) => { if (data && !('detail' in data)) setPortfolio(data); })
        .catch(() => {});
    };
    poll();
    const id = setInterval(poll, intervalMs);
    return () => clearInterval(id);
  }, [setPortfolio, intervalMs]);
}
