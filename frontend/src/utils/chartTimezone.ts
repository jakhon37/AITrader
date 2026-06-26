import type { Time } from 'lightweight-charts';

export const CHART_TIMEZONE_STORAGE_KEY = 'terminal_chart_timezone';

/** Use browser IANA zone; re-resolved when the user picks "Local". */
export const BROWSER_TIMEZONE_VALUE = 'browser';

export const CHART_TIMEZONE_PRESETS = [
  { value: BROWSER_TIMEZONE_VALUE, label: 'Local' },
  { value: 'UTC', label: 'UTC' },
  { value: 'Asia/Seoul', label: 'Seoul' },
  { value: 'Asia/Tashkent', label: 'Tashkent' },
  { value: 'America/New_York', label: 'New York' },
  { value: 'Europe/London', label: 'London' },
] as const;

export function getBrowserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
}

export function resolveChartTimezone(stored: string | null): string {
  if (!stored || stored === BROWSER_TIMEZONE_VALUE) {
    return getBrowserTimezone();
  }
  return stored;
}

export function loadStoredChartTimezone(): string | null {
  try {
    return localStorage.getItem(CHART_TIMEZONE_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function saveChartTimezone(timezone: string): void {
  try {
    localStorage.setItem(CHART_TIMEZONE_STORAGE_KEY, timezone);
  } catch {
    /* ignore quota / private mode */
  }
}

export function formatTimezoneShort(timezone: string): string {
  const resolved = resolveChartTimezone(timezone);
  try {
    const parts = new Intl.DateTimeFormat('en', {
      timeZone: resolved,
      timeZoneName: 'short',
    }).formatToParts(new Date());
    return parts.find((p) => p.type === 'timeZoneName')?.value ?? resolved;
  } catch {
    return resolved;
  }
}

function calendarDayKey(date: Date, timezone: string): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: timezone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date);
}

/** Format an ISO UTC timestamp for calendar panels using the chart timezone. */
export function formatCalendarEventTime(iso: string, timezone: string): string {
  const resolved = resolveChartTimezone(timezone);
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }

  const sameDay = calendarDayKey(date, resolved) === calendarDayKey(new Date(), resolved);
  const options: Intl.DateTimeFormatOptions = {
    timeZone: resolved,
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  };
  if (!sameDay) {
    options.day = 'numeric';
    options.month = 'short';
  }

  try {
    return new Intl.DateTimeFormat('en-GB', options).format(date);
  } catch {
    return date.toISOString();
  }
}

function timeToUnixSeconds(time: Time): number {
  if (typeof time === 'number') return time;
  if (typeof time === 'string') return Math.floor(new Date(time).getTime() / 1000);
  if (time && typeof time === 'object' && 'year' in time) {
    return Math.floor(Date.UTC(time.year, time.month - 1, time.day) / 1000);
  }
  return 0;
}

type TickMarkKind = number;

const TICK_YEAR = 0;
const TICK_MONTH = 1;
const TICK_DAY = 2;
const TICK_TIME = 3;
const TICK_TIME_WITH_SECONDS = 4;

function formatInZone(
  unixSec: number,
  timezone: string,
  options: Intl.DateTimeFormatOptions,
): string {
  return new Intl.DateTimeFormat('en-GB', {
    ...options,
    timeZone: timezone,
  }).format(new Date(unixSec * 1000));
}

export function createChartTimezoneFormatters(timezone: string) {
  const resolved = resolveChartTimezone(timezone);

  const formatCrosshair = (time: Time): string => {
    const unix = timeToUnixSeconds(time);
    if (!unix) return '';
    return formatInZone(unix, resolved, {
      year: 'numeric',
      month: 'short',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
  };

  const formatTickMark = (
    time: Time,
    tickMarkType: TickMarkKind,
    _locale: string,
  ): string | null => {
    const unix = timeToUnixSeconds(time);
    if (!unix) return null;

    switch (tickMarkType) {
      case TICK_YEAR:
        return formatInZone(unix, resolved, { year: 'numeric' });
      case TICK_MONTH:
        return formatInZone(unix, resolved, { month: 'short', year: '2-digit' });
      case TICK_DAY:
        return formatInZone(unix, resolved, { day: 'numeric', month: 'short' });
      case TICK_TIME_WITH_SECONDS:
        return formatInZone(unix, resolved, {
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
          hour12: false,
        });
      case TICK_TIME:
      default:
        return formatInZone(unix, resolved, {
          hour: '2-digit',
          minute: '2-digit',
          hour12: false,
        });
    }
  };

  return {
    resolved,
    timeFormatter: formatCrosshair,
    tickMarkFormatter: formatTickMark,
  };
}