import { useEffect } from 'react';

interface WebSocketHookOptions {
  instrument: string;
  timeframe: string;
  onNewBar?: (bar: any) => void;
  updateBar: (bar: any) => void;
}

export function useChartWebSocket({
  instrument,
  timeframe,
  onNewBar,
  updateBar,
}: WebSocketHookOptions) {
  useEffect(() => {
    const handleOhlcvBar = (e: Event) => {
      const customEvent = e as CustomEvent<{ instrument: string; timeframe: string; bar: any }>;
      const { instrument: barInst, timeframe: barTf, bar } = customEvent.detail;
      if (barInst.toUpperCase() === instrument.toUpperCase() && barTf === timeframe) {
        updateBar(bar);
        if (onNewBar) {
          onNewBar(bar);
        }
      }
    };
    window.addEventListener('ohlcv_bar', handleOhlcvBar);

    const handleReplayFrame = (e: Event) => {
      const customEvent = e as CustomEvent<{ bar: any }>;
      const { bar } = customEvent.detail;
      if (!bar) return;
      const dt = new Date(bar.timestamp);
      const unixSeconds = Math.floor(dt.getTime() / 1000);
      const ohlcvBar = {
        time: unixSeconds,
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
        volume: bar.volume,
      };
      if (
        bar.instrument.toUpperCase() === instrument.toUpperCase() &&
        (bar.timeframe === timeframe || (bar.timeframe === '1m' && timeframe === '1m'))
      ) {
        updateBar(ohlcvBar);
        if (onNewBar) {
          onNewBar(ohlcvBar);
        }
      }
    };
    window.addEventListener('replay_frame', handleReplayFrame);

    return () => {
      window.removeEventListener('ohlcv_bar', handleOhlcvBar);
      window.removeEventListener('replay_frame', handleReplayFrame);
    };
  }, [instrument, timeframe, onNewBar, updateBar]);
}
