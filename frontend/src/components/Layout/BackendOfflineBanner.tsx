interface Props {
  visible: boolean;
}

export function BackendOfflineBanner({ visible }: Props) {
  if (!visible) return null;

  return (
    <div
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        zIndex: 100000,
        background: 'rgba(255, 23, 68, 0.92)',
        color: '#fff',
        padding: '10px 16px',
        fontSize: 13,
        fontWeight: 600,
        textAlign: 'center',
        boxShadow: '0 2px 12px rgba(0,0,0,0.35)',
      }}
    >
      Backend offline — start the API with{' '}
      <code style={{ background: 'rgba(0,0,0,0.25)', padding: '2px 6px', borderRadius: 4 }}>
        ./scripts/start_webui.sh
      </code>{' '}
      or{' '}
      <code style={{ background: 'rgba(0,0,0,0.25)', padding: '2px 6px', borderRadius: 4 }}>
        docker start aitrader-webui-backend
      </code>
      . Retrying…
    </div>
  );
}