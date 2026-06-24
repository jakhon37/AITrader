import { useEffect, useState } from 'react';
import type { IChartApi, ISeriesApi } from 'lightweight-charts';
import type { Point } from '../drawingTypes';

export function useCanvasPosition(
  chart: IChartApi,
  candleSeries: ISeriesApi<'Candlestick'>,
  containerRef: React.RefObject<HTMLDivElement | null>,
  canvasRef: React.RefObject<HTMLCanvasElement | null>
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
    const x = chart.timeScale().timeToCoordinate(pt.time as any);
    const y = candleSeries.priceToCoordinate(pt.price);
    return { x, y };
  };

  const mapPixelsToPoint = (clientX: number, clientY: number) => {
    if (!canvasRef.current) return null;
    const rect = canvasRef.current.getBoundingClientRect();
    const x = clientX - rect.left;
    const y = clientY - rect.top;

    const time = chart.timeScale().coordinateToTime(x);
    const price = candleSeries.coordinateToPrice(y);

    if (time === null || price === null) return null;
    return { time: Number(time), price };
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
