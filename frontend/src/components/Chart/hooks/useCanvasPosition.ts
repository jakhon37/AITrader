import { useEffect, useState, type MutableRefObject } from 'react';
import type { IChartApi, ISeriesApi } from 'lightweight-charts';
import type { Point } from '../drawingTypes';
import { findClosestBarIndex } from '../utils';

export function useCanvasPosition(
  chart: IChartApi,
  candleSeries: ISeriesApi<'Candlestick'>,
  containerRef: React.RefObject<HTMLDivElement | null>,
  canvasRef: React.RefObject<HTMLCanvasElement | null>,
  barTimesRef: MutableRefObject<number[]>,
) {
  const [position, setPosition] = useState({ left: 0, top: 0, width: 0, height: 0 });

  useEffect(() => {
    if (!containerRef.current) return;

    const updatePosition = () => {
      const cell = containerRef.current?.querySelector('canvas');
      const cellElement = cell?.parentElement;
      if (cellElement) {
        const cellRect = cellElement.getBoundingClientRect();
        const containerRect = containerRef.current!.getBoundingClientRect();

        setPosition({
          left: cellRect.left - containerRect.left,
          top: cellRect.top - containerRect.top,
          width: cellRect.width,
          height: cellRect.height,
        });
      }
    };

    updatePosition();

    const ro = new ResizeObserver(updatePosition);
    ro.observe(containerRef.current);

    window.addEventListener('resize', updatePosition);
    return () => {
      ro.disconnect();
      window.removeEventListener('resize', updatePosition);
    };
  }, [containerRef, chart]);

  const mapPointToPixels = (pt: Point) => {
    const barTimes = barTimesRef.current;
    let x: number | null = null;

    if (barTimes.length > 0) {
      const idx = findClosestBarIndex(barTimes, pt.time);
      if (idx !== -1) {
        x = chart.timeScale().logicalToCoordinate(idx);
        if (x === null) {
          x = chart.timeScale().timeToCoordinate(barTimes[idx] as never);
        }
      }
    } else {
      x = chart.timeScale().timeToCoordinate(pt.time as never);
    }

    const y = candleSeries.priceToCoordinate(pt.price);
    return { x, y };
  };

  const mapPixelsToPoint = (clientX: number, clientY: number) => {
    if (!canvasRef.current) return null;
    const rect = canvasRef.current.getBoundingClientRect();
    const x = clientX - rect.left;
    const y = clientY - rect.top;

    const price = candleSeries.coordinateToPrice(y);
    if (price === null) return null;

    const barTimes = barTimesRef.current;
    let time: number | null = null;

    if (barTimes.length > 0) {
      const logical = chart.timeScale().coordinateToLogical(x);
      if (logical === null) return null;
      const idx = Math.max(0, Math.min(barTimes.length - 1, Math.round(logical)));
      time = barTimes[idx];
    } else {
      const rawTime = chart.timeScale().coordinateToTime(x);
      if (rawTime === null) return null;
      time = Number(rawTime);
    }

    return { time, price };
  };

  const mapPixelToPrice = (clientY: number) => {
    if (!canvasRef.current) return null;
    const rect = canvasRef.current.getBoundingClientRect();
    const y = clientY - rect.top;
    return candleSeries.coordinateToPrice(y);
  };

  const mapPriceToY = (price: number) => {
    return candleSeries.priceToCoordinate(price);
  };

  return { position, mapPointToPixels, mapPixelsToPoint, mapPixelToPrice, mapPriceToY };
}