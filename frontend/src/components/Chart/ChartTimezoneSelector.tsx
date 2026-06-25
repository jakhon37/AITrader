import {
  BROWSER_TIMEZONE_VALUE,
  CHART_TIMEZONE_PRESETS,
  getBrowserTimezone,
} from '../../utils/chartTimezone';

interface Props {
  timezone: string;
  onChange: (timezone: string) => void;
}

const selectStyle: React.CSSProperties = {
  background: '#111827',
  color: 'var(--text-secondary)',
  border: '1px solid var(--border-glow)',
  borderRadius: 6,
  padding: '4px 8px',
  fontSize: 11,
  fontWeight: 600,
  outline: 'none',
  cursor: 'pointer',
};

export function ChartTimezoneSelector({ timezone, onChange }: Props) {
  const browserTz = getBrowserTimezone();

  return (
    <select
      style={selectStyle}
      value={timezone}
      onChange={(e) => onChange(e.target.value)}
      title="Chart display timezone (stored data remains UTC)"
    >
      {CHART_TIMEZONE_PRESETS.map((preset) => {
        const label =
          preset.value === BROWSER_TIMEZONE_VALUE
            ? `Local (${browserTz})`
            : preset.label;
        return (
          <option key={preset.value} value={preset.value}>
            {label}
          </option>
        );
      })}
    </select>
  );
}