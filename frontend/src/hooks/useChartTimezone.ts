import { useCallback, useEffect, useState } from 'react';
import {
  BROWSER_TIMEZONE_VALUE,
  formatTimezoneShort,
  loadStoredChartTimezone,
  resolveChartTimezone,
  saveChartTimezone,
} from '../utils/chartTimezone';

const TIMEZONE_CHANGE_EVENT = 'chart-timezone-change';

export function useChartTimezone() {
  const [stored, setStored] = useState<string | null>(() => loadStoredChartTimezone());

  useEffect(() => {
    const sync = () => setStored(loadStoredChartTimezone());
    window.addEventListener(TIMEZONE_CHANGE_EVENT, sync);
    window.addEventListener('storage', sync);
    return () => {
      window.removeEventListener(TIMEZONE_CHANGE_EVENT, sync);
      window.removeEventListener('storage', sync);
    };
  }, []);

  const setTimezone = useCallback((timezone: string) => {
    saveChartTimezone(timezone);
    setStored(timezone);
    window.dispatchEvent(new CustomEvent(TIMEZONE_CHANGE_EVENT, { detail: timezone }));
  }, []);

  const timezone = stored ?? BROWSER_TIMEZONE_VALUE;
  const resolved = resolveChartTimezone(timezone);
  const displayLabel = formatTimezoneShort(timezone);

  return {
    timezone,
    setTimezone,
    resolved,
    displayLabel,
    isBrowserDefault: stored === null || stored === BROWSER_TIMEZONE_VALUE,
  };
}