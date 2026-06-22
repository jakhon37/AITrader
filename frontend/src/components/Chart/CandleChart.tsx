import { useEffect, useRef } from 'react';
import { createChart, CandlestickSeries, HistogramSeries } from 'lightweight-charts';
import type { IChartApi, ISeriesApi, Time } from 'lightweight-charts';
import { getOHLCV } from '../../api/client';

interface Props {
  instrument: string;
  timeframe: string;
  onNewBar?: (bar: { time: number; open: number; high: number; low: number; close: number; volume: number }) => void;
  virtualEndTime?: string; // ISO string representing active replay timestamp
}

const LOOKBACK: Record<string, number> = {
  '1m': 30, '5m': 90, '15m': 180, '30m': 365, '1h': 1500, '4h': 3650, '1d': 3650, '1w': 3650,
};

const MAX_BUFFER = 20000;

const PAGINATION_LOOKBACK: Record<string, number> = {
  '1m': 2,
  '5m': 7,
  '15m': 20,
  '30m': 40,
  '1h': 80,
  '4h': 300,
  '1d': 1000,
  '1w': 5000,
};

const findClosestIndex = (data: { time: number }[], targetTime: number): number => {
  if (data.length === 0) return -1;
  let closestIdx = 0;
  let minDiff = Math.abs(data[0].time - targetTime);
  for (let i = 1; i < data.length; i++) {
    const diff = Math.abs(data[i].time - targetTime);
    if (diff < minDiff) {
      minDiff = diff;
      closestIdx = i;
    }
  }
  return closestIdx;
};

export function CandleChart({ instrument, timeframe, onNewBar, virtualEndTime }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volumeRef = useRef<ISeriesApi<'Histogram'> | null>(null);

  // Expose update function via a stable ref so WS messages can call it without re-render
  const updateBarRef = useRef<((bar: { time: number; open: number; high: number; low: number; close: number; volume: number }) => void) | null>(null);

  // Persistent refs to track state across useEffect re-runs
  const lastVisibleTimeRef = useRef<number | null>(null);
  const lastVisibleBarsCountRef = useRef<number>(150);
  const prevTimeframeRef = useRef<string>(timeframe);
  const prevInstrumentRef = useRef<string>(instrument);
  const lastLoadedEndTimeRef = useRef<string | undefined>(undefined);

  useEffect(() => {
    if (!containerRef.current) return;

    // Check if this is just a sequential tick during replay or streaming
    let isReplayTick = false;
    if (
      chartRef.current &&
      prevInstrumentRef.current === instrument &&
      prevTimeframeRef.current === timeframe &&
      lastLoadedEndTimeRef.current &&
      virtualEndTime
    ) {
      const prevMs = Date.parse(lastLoadedEndTimeRef.current);
      const newMs = Date.parse(virtualEndTime);
      if (!isNaN(prevMs) && !isNaN(newMs)) {
        const diffMs = newMs - prevMs;
        // Treat as a replay tick if the time difference is small (e.g., within 1 day)
        if (diffMs >= 0 && diffMs < 86400_000) {
          isReplayTick = true;
        }
      }
    }

    lastLoadedEndTimeRef.current = virtualEndTime;

    if (isReplayTick) {
      prevInstrumentRef.current = instrument;
      prevTimeframeRef.current = timeframe;
      return;
    }

    // Tear down previous chart since it's a real change (instrument, timeframe, or large jump)
    if (chartRef.current) {
      try { chartRef.current.remove(); } catch { /* ignore */ }
      chartRef.current = null;
    }

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth || 600,
      height: containerRef.current.clientHeight || 380,
      layout: { background: { color: '#0d1322' }, textColor: '#8e9bb4' },
      grid: {
        vertLines: { visible: false },
        horzLines: { color: 'rgba(255,255,255,0.03)' },
      },
      crosshair: { mode: 1 },
      timeScale: { borderColor: 'rgba(255,255,255,0.08)', timeVisible: true },
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#00e676', downColor: '#ff1744',
      borderUpColor: '#00e676', borderDownColor: '#ff1744',
      wickUpColor: '#00e676', wickDownColor: '#ff1744',
    });

    const volumeSeries = chart.addSeries(HistogramSeries, {
      color: '#00e5ff',
      priceFormat: { type: 'volume' },
      priceScaleId: '',
    });
    volumeSeries.priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });

    chartRef.current = chart;
    candleRef.current = candleSeries;
    volumeRef.current = volumeSeries;

    let loadedData: { time: number; open: number; high: number; low: number; close: number; volume: number }[] = [];
    let isFetching = false;
    let hasMoreHistory = true;
    let hasNewerHistory = false;

    // Stable update function
    updateBarRef.current = (bar) => {
      if (!candleRef.current || !volumeRef.current) return;

      if (hasNewerHistory) {
        // If we have evicted newer history, just update existing bar if present,
        // but do not append new bars to prevent gaps in data.
        const idx = loadedData.findIndex((d) => d.time === bar.time);
        if (idx !== -1) {
          loadedData[idx] = bar;
          candleRef.current.update({ time: bar.time as Time, open: bar.open, high: bar.high, low: bar.low, close: bar.close });
          volumeRef.current.update({
            time: bar.time as Time,
            value: bar.volume,
            color: bar.close >= bar.open ? 'rgba(0,230,118,0.3)' : 'rgba(255,23,68,0.3)',
          });
        }
        return;
      }

      candleRef.current.update({ time: bar.time as Time, open: bar.open, high: bar.high, low: bar.low, close: bar.close });
      volumeRef.current.update({
        time: bar.time as Time,
        value: bar.volume,
        color: bar.close >= bar.open ? 'rgba(0,230,118,0.3)' : 'rgba(255,23,68,0.3)',
      });

      // Update local data cache to keep it in sync with new bars
      const idx = loadedData.findIndex((d) => d.time === bar.time);
      if (idx !== -1) {
        loadedData[idx] = bar;
      } else {
        loadedData.push(bar);
        loadedData.sort((a, b) => a.time - b.time);
        if (loadedData.length > MAX_BUFFER) {
          loadedData = loadedData.slice(loadedData.length - MAX_BUFFER);
          hasMoreHistory = true; // Evicted older data from the left
          candleSeries.setData(loadedData.map((d) => ({ time: d.time as Time, open: d.open, high: d.high, low: d.low, close: d.close })));
          volumeSeries.setData(loadedData.map((d) => ({ time: d.time as Time, value: d.volume ?? 0, color: d.close >= d.open ? 'rgba(0,230,118,0.3)' : 'rgba(255,23,68,0.3)' })));
        }
      }
    };

    // If the instrument changed, reset the saved scroll position
    if (prevInstrumentRef.current !== instrument) {
      lastVisibleTimeRef.current = null;
      prevInstrumentRef.current = instrument;
    }

    // Determine the end timestamp to load
    let end: string;
    const isTimeframeChange = prevTimeframeRef.current !== timeframe && lastVisibleTimeRef.current !== null;
    if (isTimeframeChange) {
      // Timeframe changed - load ending at the exact time we stopped at
      end = new Date(lastVisibleTimeRef.current! * 1000).toISOString();
    } else {
      // Replay tick, reset, or initial load - load ending at current virtual/live time
      end = virtualEndTime || new Date().toISOString();
      lastVisibleTimeRef.current = null;
    }

    // Keep track of the current timeframe for the next re-run
    prevTimeframeRef.current = timeframe;

    // Load initial historical data
    const days = LOOKBACK[timeframe] ?? 30;
    const endDate = new Date(end);
    const start = new Date(endDate.getTime() - days * 86400_000).toISOString();

    getOHLCV(instrument, timeframe, start, end)
      .then((data: { time: number; open: number; high: number; low: number; close: number; volume: number }[]) => {
        if (!Array.isArray(data) || data.length === 0) {
          hasMoreHistory = false;
          return;
        }

        // Respect MAX_BUFFER in initial load
        if (data.length > MAX_BUFFER) {
          loadedData = data.slice(data.length - MAX_BUFFER);
          hasMoreHistory = true;
        } else {
          loadedData = data;
        }

        candleSeries.setData(loadedData.map((d) => ({ time: d.time as Time, open: d.open, high: d.high, low: d.low, close: d.close })));
        volumeSeries.setData(loadedData.map((d) => ({ time: d.time as Time, value: d.volume ?? 0, color: d.close >= d.open ? 'rgba(0,230,118,0.3)' : 'rgba(255,23,68,0.3)' })));

        if (isTimeframeChange && lastVisibleTimeRef.current !== null) {
          const targetIndex = findClosestIndex(loadedData, lastVisibleTimeRef.current);
          if (targetIndex !== -1) {
            const barsCount = lastVisibleBarsCountRef.current || 150;
            chart.timeScale().setVisibleLogicalRange({
              from: targetIndex - barsCount,
              to: targetIndex,
            });
          } else {
            chart.timeScale().fitContent();
          }
        } else {
          chart.timeScale().fitContent();
        }
      })
      .catch(console.error);

    // Scroll listener for lazy loading historical data (bi-directional with eviction)
    const handleVisibleLogicalRangeChange = async (newVisibleRange: any) => {
      if (!newVisibleRange || isFetching || loadedData.length === 0) return;

      // 1. Trigger older history load when close to left boundary
      if (newVisibleRange.from < 15 && hasMoreHistory) {
        isFetching = true;
        try {
          const oldestTime = loadedData[0].time;
          const oldestDate = new Date(oldestTime * 1000);

          const daysToLoad = PAGINATION_LOOKBACK[timeframe] ?? 30;
          const chunkStart = new Date(oldestDate.getTime() - daysToLoad * 86400_000).toISOString();
          const chunkEnd = oldestDate.toISOString();

          const newChunk = await getOHLCV(instrument, timeframe, chunkStart, chunkEnd);

          if (!Array.isArray(newChunk) || newChunk.length === 0) {
            hasMoreHistory = false;
            return;
          }

          // Exclude overlap
          const filteredChunk = newChunk.filter((d) => d.time < oldestTime);
          if (filteredChunk.length === 0) {
            hasMoreHistory = false;
            return;
          }

          const merged = [...filteredChunk, ...loadedData];

          // Perform eviction if merged exceeds MAX_BUFFER
          let finalData = merged;
          if (merged.length > MAX_BUFFER) {
            finalData = merged.slice(0, MAX_BUFFER);
            hasNewerHistory = true; // We just evicted newer data on the right
          }

          loadedData = finalData;

          // Prevent viewport jump by shifting the visible logical range.
          // Capture current visible range BEFORE setting updated series data.
          const currentVisibleRange = chart.timeScale().getVisibleLogicalRange();
          const addedBarsCount = filteredChunk.length;

          // Set the updated series data
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
          isFetching = false;
        }
      }
      // 2. Trigger newer history load when close to right boundary AND there is evicted newer history
      else if (newVisibleRange.to > loadedData.length - 15 && hasNewerHistory) {
        isFetching = true;
        try {
          const newestTime = loadedData[loadedData.length - 1].time;
          const newestDate = new Date(newestTime * 1000);

          const daysToLoad = PAGINATION_LOOKBACK[timeframe] ?? 30;
          const chunkStart = newestDate.toISOString();
          const limitEnd = virtualEndTime || new Date().toISOString();
          const targetEnd = new Date(newestDate.getTime() + daysToLoad * 86400_000).toISOString();
          const chunkEnd = new Date(targetEnd) > new Date(limitEnd) ? limitEnd : targetEnd;

          if (new Date(chunkStart) >= new Date(limitEnd)) {
            hasNewerHistory = false;
            return;
          }

          const newChunk = await getOHLCV(instrument, timeframe, chunkStart, chunkEnd);

          if (!Array.isArray(newChunk) || newChunk.length === 0) {
            hasNewerHistory = false;
            return;
          }

          // Exclude overlap
          const filteredChunk = newChunk.filter((d) => d.time > newestTime);
          if (filteredChunk.length === 0) {
            hasNewerHistory = false;
            return;
          }

          const merged = [...loadedData, ...filteredChunk];

          // Perform eviction if merged exceeds MAX_BUFFER
          let removedFromLeft = 0;
          let finalData = merged;
          if (merged.length > MAX_BUFFER) {
            removedFromLeft = merged.length - MAX_BUFFER;
            finalData = merged.slice(removedFromLeft);
            hasMoreHistory = true; // We just evicted older data on the left
          }

          loadedData = finalData;

          // Capture visible range BEFORE setting updated series data
          const currentVisibleRange = chart.timeScale().getVisibleLogicalRange();

          // Set the updated series data
          candleSeries.setData(finalData.map((d) => ({ time: d.time as Time, open: d.open, high: d.high, low: d.low, close: d.close })));
          volumeSeries.setData(finalData.map((d) => ({ time: d.time as Time, value: d.volume ?? 0, color: d.close >= d.open ? 'rgba(0,230,118,0.3)' : 'rgba(255,23,68,0.3)' })));

          if (currentVisibleRange) {
            chart.timeScale().setVisibleLogicalRange({
              from: currentVisibleRange.from - removedFromLeft,
              to: currentVisibleRange.to - removedFromLeft,
            });
          }

          if (new Date(chunkEnd) >= new Date(limitEnd)) {
            hasNewerHistory = false;
          }
        } catch (err) {
          console.error('Error fetching newer chart history:', err);
        } finally {
          isFetching = false;
        }
      }
    };

    chart.timeScale().subscribeVisibleLogicalRangeChange(handleVisibleLogicalRangeChange);

    // Event listener for real-time bars from WebSocket
    const handleOhlcvBar = (e: Event) => {
      const customEvent = e as CustomEvent<{ instrument: string; timeframe: string; bar: any }>;
      const { instrument: barInst, timeframe: barTf, bar } = customEvent.detail;
      if (barInst.toUpperCase() === instrument.toUpperCase() && barTf === timeframe) {
        if (updateBarRef.current) {
          updateBarRef.current(bar);
        }
        if (onNewBar) {
          onNewBar(bar);
        }
      }
    };
    window.addEventListener('ohlcv_bar', handleOhlcvBar);

    // Event listener for replay frames
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
      if (bar.instrument.toUpperCase() === instrument.toUpperCase() && (bar.timeframe === timeframe || (bar.timeframe === '1m' && timeframe === '1m'))) {
        if (updateBarRef.current) {
          updateBarRef.current(ohlcvBar);
        }
        if (onNewBar) {
          onNewBar(ohlcvBar);
        }
      }
    };
    window.addEventListener('replay_frame', handleReplayFrame);

    // Resize observer
    const ro = new ResizeObserver((entries) => {
      if (!chartRef.current || !entries[0]) return;
      const { width, height } = entries[0].contentRect;
      chartRef.current.resize(width, height);
    });
    ro.observe(containerRef.current);

    return () => {
      window.removeEventListener('ohlcv_bar', handleOhlcvBar);
      window.removeEventListener('replay_frame', handleReplayFrame);

      // Save the last visible timestamp and zoom level before tearing down the chart
      if (chartRef.current) {
        try {
          const visibleRange = chartRef.current.timeScale().getVisibleRange();
          if (visibleRange && visibleRange.to) {
            const toTime = visibleRange.to;
            if (typeof toTime === 'number') {
              lastVisibleTimeRef.current = toTime;
            } else if (typeof toTime === 'string') {
              const parsed = Date.parse(toTime);
              if (!isNaN(parsed)) {
                lastVisibleTimeRef.current = Math.floor(parsed / 1000);
              }
            }
          }
          const logicalRange = chartRef.current.timeScale().getVisibleLogicalRange();
          if (logicalRange) {
            lastVisibleBarsCountRef.current = logicalRange.to - logicalRange.from;
          }
        } catch (e) {
          /* ignore */
        }
      }

      try {
        chart.timeScale().unsubscribeVisibleLogicalRangeChange(handleVisibleLogicalRangeChange);
      } catch { /* ignore */ }
      ro.disconnect();
      try { chart.remove(); } catch { /* ignore */ }
      chartRef.current = null;
      candleRef.current = null;
      volumeRef.current = null;
    };
  }, [instrument, timeframe, onNewBar, virtualEndTime]);

  return <div ref={containerRef} style={{ width: '100%', height: '100%' }} />;
}
