import { useEffect } from 'react';
import type { MutableRefObject } from 'react';
import type { IChartApi, ISeriesApi, Time } from 'lightweight-charts';
import { getOHLCV } from '../../../api/client';
import { MAX_BUFFER, PAGINATION_LOOKBACK, isTradingBar } from '../utils';

interface ScrollingHookOptions {
  chart: IChartApi | null;
  candleSeries: ISeriesApi<'Candlestick'> | null;
  volumeSeries: ISeriesApi<'Histogram'> | null;
  instrument: string;
  timeframe: string;
  virtualEndTimeRef: MutableRefObject<string | undefined>;
  dataRef: MutableRefObject<any[]>;
  paginationRef: MutableRefObject<{
    isFetching: boolean;
    hasMoreHistory: boolean;
    hasNewerHistory: boolean;
  }>;
}

export function useChartScrolling({
  chart,
  candleSeries,
  volumeSeries,
  instrument,
  timeframe,
  virtualEndTimeRef,
  dataRef,
  paginationRef,
}: ScrollingHookOptions) {
  useEffect(() => {
    if (!chart || !candleSeries || !volumeSeries) return;

    const handleVisibleLogicalRangeChange = async (newVisibleRange: any) => {
      const pag = paginationRef.current;
      if (!newVisibleRange || pag.isFetching || dataRef.current.length === 0) return;

      // 1. Trigger older history load when close to left boundary
      if (newVisibleRange.from < 15 && pag.hasMoreHistory) {
        pag.isFetching = true;
        try {
          const oldestTime = dataRef.current[0].time;
          const oldestDate = new Date(oldestTime * 1000);

          const fetchOlder = async (lookbackDays: number, attempt: number): Promise<any[]> => {
            const chunkStart = new Date(oldestDate.getTime() - lookbackDays * 86400_000).toISOString();
            const chunkEnd = oldestDate.toISOString();
            const chunk = await getOHLCV(instrument, timeframe, chunkStart, chunkEnd);
            const filtered = Array.isArray(chunk) ? chunk.filter(isTradingBar).filter((d) => d.time < oldestTime) : [];

            if (filtered.length === 0 && attempt < 3) {
              // Expand window recursively (adding 5 days) to skip weekend/holiday gaps
              return fetchOlder(lookbackDays + 5, attempt + 1);
            }
            return filtered;
          };

          const initialDays = PAGINATION_LOOKBACK[timeframe] ?? 30;
          const filteredChunk = await fetchOlder(initialDays, 1);
          if (filteredChunk.length === 0) {
            pag.hasMoreHistory = false;
            return;
          }

          const merged = [...filteredChunk, ...dataRef.current];
          let finalData = merged;
          if (merged.length > MAX_BUFFER) {
            finalData = merged.slice(0, MAX_BUFFER);
            pag.hasNewerHistory = true;
          }

          dataRef.current = finalData;

          const currentVisibleRange = chart.timeScale().getVisibleLogicalRange();
          const addedBarsCount = filteredChunk.length;

          candleSeries.setData(finalData.map((d) => ({ time: d.time as Time, open: d.open, high: d.high, low: d.low, close: d.close })));
          volumeSeries.setData(finalData.map((d) => ({ time: d.time as Time, value: d.volume ?? 0, color: d.close >= d.open ? 'rgba(0,230,118,0.3)' : 'rgba(255,23,68,0.3)' })));

          if (currentVisibleRange) {
            chart.timeScale().setVisibleLogicalRange({
              from: currentVisibleRange.from + addedBarsCount,
              to: currentVisibleRange.to + addedBarsCount,
            });
          }
        } catch (err) {
          console.error('Error fetching older chart history:', err);
        } finally {
          pag.isFetching = false;
        }
      }
      // 2. Trigger newer history load when close to right boundary
      else if (newVisibleRange.to > dataRef.current.length - 15 && pag.hasNewerHistory) {
        pag.isFetching = true;
        try {
          const newestTime = dataRef.current[dataRef.current.length - 1].time;
          const newestDate = new Date(newestTime * 1000);
          const daysToLoad = PAGINATION_LOOKBACK[timeframe] ?? 30;
          const chunkStart = newestDate.toISOString();
          const limitEnd = virtualEndTimeRef.current || new Date().toISOString();
          const targetEnd = new Date(newestDate.getTime() + daysToLoad * 86400_000).toISOString();
          const chunkEnd = new Date(targetEnd) > new Date(limitEnd) ? limitEnd : targetEnd;

          if (new Date(chunkStart) >= new Date(limitEnd)) {
            pag.hasNewerHistory = false;
            return;
          }

          const newChunk = await getOHLCV(instrument, timeframe, chunkStart, chunkEnd);
          if (!Array.isArray(newChunk) || newChunk.length === 0) {
            pag.hasNewerHistory = false;
            return;
          }

          const filteredChunk = newChunk.filter(isTradingBar).filter((d) => d.time > newestTime);
          if (filteredChunk.length === 0) {
            pag.hasNewerHistory = false;
            return;
          }

          const merged = [...dataRef.current, ...filteredChunk];
          let removedFromLeft = 0;
          let finalData = merged;
          if (merged.length > MAX_BUFFER) {
            removedFromLeft = merged.length - MAX_BUFFER;
            finalData = merged.slice(removedFromLeft);
            pag.hasMoreHistory = true;
          }

          dataRef.current = finalData;

          const currentVisibleRange = chart.timeScale().getVisibleLogicalRange();

          candleSeries.setData(finalData.map((d) => ({ time: d.time as Time, open: d.open, high: d.high, low: d.low, close: d.close })));
          volumeSeries.setData(finalData.map((d) => ({ time: d.time as Time, value: d.volume ?? 0, color: d.close >= d.open ? 'rgba(0,230,118,0.3)' : 'rgba(255,23,68,0.3)' })));

          if (currentVisibleRange) {
            chart.timeScale().setVisibleLogicalRange({
              from: currentVisibleRange.from - removedFromLeft,
              to: currentVisibleRange.to - removedFromLeft,
            });
          }

          if (new Date(chunkEnd) >= new Date(limitEnd)) {
            pag.hasNewerHistory = false;
          }
        } catch (err) {
          console.error('Error fetching newer chart history:', err);
        } finally {
          pag.isFetching = false;
        }
      }
    };

    chart.timeScale().subscribeVisibleLogicalRangeChange(handleVisibleLogicalRangeChange);

    return () => {
      try {
        chart.timeScale().unsubscribeVisibleLogicalRangeChange(handleVisibleLogicalRangeChange);
      } catch { /* ignore */ }
    };
  }, [chart, candleSeries, volumeSeries, instrument, timeframe, virtualEndTimeRef, dataRef, paginationRef]);
}
