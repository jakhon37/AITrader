import { useEffect, useState } from 'react';
import { getHealth } from '../api/client';

export function useBackendHealth(pollMs = 5000) {
  const [apiOnline, setApiOnline] = useState<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;

    const check = async () => {
      try {
        await getHealth();
        if (!cancelled) setApiOnline(true);
      } catch {
        if (!cancelled) setApiOnline(false);
      }
    };

    check();
    const id = window.setInterval(check, pollMs);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [pollMs]);

  return apiOnline;
}