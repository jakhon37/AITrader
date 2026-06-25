import { useEffect, type MutableRefObject } from 'react';

interface WebSocketHookOptions {
  instrument: string;
  timeframe: string;
  onNewBar?: (bar: any) => void;
  updateBar: (bar: any) => void;
  /** When set, the chart is in replay mode — ignore live ohlcv_bar feeds. */
  virtualEndTimeRef?: MutableRefObject<string | undefined>;
}

export function useChartWebSocket({
  instrument,
  timeframe,
  onNewBar,
  updateBar,
  virtualEndTimeRef,
}: WebSocketHookOptions) {
  useEffect(() => {
    const handleOhlcvBar = (e: Event) => {
      // During replay, bars arrive via replay_frame only. Live scheduler bars
      // (registered when the chart fetches history) carry far-future timestamps
      // and freeze the price-line indicator on a stale value.
      if (virtualEndTimeRef?.current) return;

      const customEvent = e as CustomEvent<{
        instrument: string;
        timeframe: string;
        source?: string;
        bar: any;
      }>;
      const { instrument: barInst, timeframe: barTf, bar } = customEvent.detail;
      const inst = String(barInst ?? '').toUpperCase();
      const tf = String(barTf ?? '');
      if (inst === instrument.toUpperCase() && tf === timeframe) {
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
  }, [instrument, timeframe, onNewBar, updateBar, virtualEndTimeRef]);
}
