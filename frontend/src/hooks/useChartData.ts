import { useCallback, useState } from 'react';
import { getOHLCV } from '../api/client';

export function useChartData(instrument: string, timeframe: string) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchRange = useCallback(
    async (start: string, end: string) => {
      setLoading(true);
      setError(null);
      try {
        return await getOHLCV(instrument, timeframe, start, end);
      } catch (e) {
        const msg = e instanceof Error ? e.message : 'Failed to load chart data';
        setError(msg);
        return [];
      } finally {
        setLoading(false);
      }
    },
    [instrument, timeframe],
  );

  return { fetchRange, loading, error };
}