/** Bridge chart HTTP/WS updates to the live status indicator. */

export type ChartBarsUpdatedDetail = {
  instrument: string;
  timeframe: string;
  lastBarAt: Date;
  close: number;
};

export function emitChartBarsUpdated(
  instrument: string,
  timeframe: string,
  bars: { time: number; close: number }[],
): void {
  if (bars.length === 0) return;
  const last = bars[bars.length - 1];
  if (!Number.isFinite(last.time) || last.time <= 0) return;

  window.dispatchEvent(
    new CustomEvent<ChartBarsUpdatedDetail>('chart_bars_updated', {
      detail: {
        instrument,
        timeframe,
        lastBarAt: new Date(last.time * 1000),
        close: last.close,
      },
    }),
  );
}