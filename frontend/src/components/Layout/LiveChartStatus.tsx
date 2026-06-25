import type { LiveChartStatus } from '../../hooks/useLiveChartStatus';

interface Props {
  status: LiveChartStatus;
  wsConnected: boolean;
  displayTimezone?: string;
}

function formatAgo(date: Date | null): string {
  if (!date) return 'never';
  const sec = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  return `${Math.floor(min / 60)}h ago`;
}

function formatSource(source: string | null): string {
  if (!source) return 'dukascopy';
  if (source === 'dukascopy_active') return 'dukascopy (forming)';
  return source;
}

export function LiveChartStatus({ status, wsConnected, displayTimezone }: Props) {
  const {
    lastUpdate,
    source,
    close,
    serverError,
    replayBlocked,
    dataFresh,
    pollFresh,
    warmingUp,
    feedOffline,
  } = status;

  let label = 'Live';
  let color = 'var(--neon-green, #00e676)';

  if (!wsConnected) {
    label = 'WS offline';
    color = '#ff5252';
  } else if (replayBlocked) {
    label = 'Replay blocking live';
    color = '#ffb74d';
  } else if (serverError) {
    label = 'Feed error';
    color = '#ff5252';
  } else if (warmingUp) {
    label = 'Polling…';
    color = '#ffb74d';
  } else if (dataFresh) {
    label = 'Live';
    color = 'var(--neon-green, #00e676)';
  } else if (feedOffline) {
    label = 'Feed offline';
    color = '#ff5252';
  } else if (pollFresh) {
    label = 'No new bar';
    color = '#ffb74d';
  } else {
    label = 'Polling…';
    color = '#ffb74d';
  }

  const indicatorOnline = dataFresh || warmingUp || pollFresh;

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'flex-end',
        gap: 2,
        fontSize: 11,
        color: 'var(--text-muted)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span
          className={`glow-indicator ${indicatorOnline && wsConnected ? 'online' : 'offline'}`}
          style={{ width: 6, height: 6 }}
        />
        <span style={{ color, fontWeight: 600 }}>{label}</span>
        <span>· {formatSource(source)}</span>
      </div>
      <div>
        {displayTimezone && (
          <span style={{ marginRight: 8 }}>Data UTC · {displayTimezone}</span>
        )}
        {typeof close === 'number' && (
          <span style={{ marginRight: 8 }}>Last {close.toFixed(5)}</span>
        )}
        <span>Updated {formatAgo(lastUpdate)}</span>
        {serverError && (
          <span style={{ color: '#ff8a80', marginLeft: 8 }} title={serverError}>
            ⚠
          </span>
        )}
      </div>
    </div>
  );
}