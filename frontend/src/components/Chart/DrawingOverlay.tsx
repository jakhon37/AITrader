import { useEffect, useRef, useState } from 'react';
import type { IChartApi, ISeriesApi } from 'lightweight-charts';

interface Point {
  time: number;
  price: number;
}

interface Drawing {
  id: string;
  type: 'line' | 'box' | 'polyline';
  points: Point[];
  color: string;
  lineWidth: number;
  fill: boolean;
  opacity: number;
}

interface DrawingOverlayProps {
  chart: IChartApi;
  candleSeries: ISeriesApi<'Candlestick'>;
  activeTool: 'select' | 'line' | 'box' | 'polyline' | 'eraser';
  setActiveTool: (tool: 'select' | 'line' | 'box' | 'polyline' | 'eraser') => void;
  drawings: Drawing[];
  setDrawings: React.Dispatch<React.SetStateAction<Drawing[]>>;
  containerRef: React.RefObject<HTMLDivElement | null>;
  currentColor: string;
  currentLineWidth: number;
  fillBox: boolean;
  currentOpacity: number;
  selectedDrawingId: string | null;
  setSelectedDrawingId: (id: string | null) => void;
}

// Convert hex color + opacity value to standard RGBA string
const hexToRgba = (hex: string, alpha: number) => {
  if (hex.startsWith('rgba') || hex.startsWith('var')) return hex;
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
};

export function DrawingOverlay({
  chart,
  candleSeries,
  activeTool,
  setActiveTool,
  drawings,
  setDrawings,
  containerRef,
  currentColor,
  currentLineWidth,
  fillBox,
  currentOpacity,
  selectedDrawingId,
  setSelectedDrawingId,
}: DrawingOverlayProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [position, setPosition] = useState({ left: 0, top: 0, width: 0, height: 0 });
  const [rangeChangeKey, setRangeChangeKey] = useState(0);

  // Drawing state
  const [isDrawing, setIsDrawing] = useState(false);
  const [tempPoints, setTempPoints] = useState<Point[]>([]);
  const [cursorPos, setCursorPos] = useState<Point | null>(null);
  const [isHoveringDrawing, setIsHoveringDrawing] = useState(false);

  // Calculate and monitor the exact position and size of the chart pane
  useEffect(() => {
    if (!containerRef.current) return;

    let intervalId: any = null;

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

        // Stop polling once the cell has a valid non-zero size
        if (cellRect.width > 0 && cellRect.height > 0 && intervalId) {
          clearInterval(intervalId);
          intervalId = null;
        }
      }
    };

    updatePosition();

    // Start a polling interval to catch the element as soon as it's fully rendered
    intervalId = setInterval(updatePosition, 100);

    // Observe container element for resizes to keep canvas aligned
    const ro = new ResizeObserver(updatePosition);
    ro.observe(containerRef.current);

    window.addEventListener('resize', updatePosition);
    return () => {
      if (intervalId) clearInterval(intervalId);
      ro.disconnect();
      window.removeEventListener('resize', updatePosition);
    };
  }, [containerRef, chart]);

  // Subscribe to chart zoom / scroll to repaint the canvas
  useEffect(() => {
    if (!chart) return;
    const handleRangeChange = () => {
      setRangeChangeKey((prev) => prev + 1);
    };
    chart.timeScale().subscribeVisibleLogicalRangeChange(handleRangeChange);
    return () => {
      try {
        chart.timeScale().unsubscribeVisibleLogicalRangeChange(handleRangeChange);
      } catch {}
    };
  }, [chart]);

  // Helper to map timestamp & price to local pixel coordinates
  const mapPointToPixels = (pt: Point) => {
    const x = chart.timeScale().timeToCoordinate(pt.time as any);
    const y = candleSeries.priceToCoordinate(pt.price);
    return { x, y };
  };

  // Helper to map mouse coordinates to timestamp & price
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

  // Distance formula for erasing tool
  const getDistanceToLine = (x: number, y: number, x1: number, y1: number, x2: number, y2: number) => {
    const A = x - x1;
    const B = y - y1;
    const C = x2 - x1;
    const D = y2 - y1;

    const dot = A * C + B * D;
    const lenSq = C * C + D * D;
    let param = -1;
    if (lenSq !== 0) param = dot / lenSq;

    let xx, yy;
    if (param < 0) {
      xx = x1;
      yy = y1;
    } else if (param > 1) {
      xx = x2;
      yy = y2;
    } else {
      xx = x1 + param * C;
      yy = y1 + param * D;
    }

    const dx = x - xx;
    const dy = y - yy;
    return Math.sqrt(dx * dx + dy * dy);
  };

  // Check if a point (x, y) is close to a drawing to erase it
  const findDrawingUnderCursor = (x: number, y: number) => {
    for (const d of drawings) {
      if (d.type === 'line' && d.points.length >= 2) {
        const p1 = mapPointToPixels(d.points[0]);
        const p2 = mapPointToPixels(d.points[1]);
        if (p1.x !== null && p1.y !== null && p2.x !== null && p2.y !== null) {
          const dist = getDistanceToLine(x, y, p1.x, p1.y, p2.x, p2.y);
          if (dist < 8) return d.id;
        }
      } else if (d.type === 'box' && d.points.length >= 2) {
        const p1 = mapPointToPixels(d.points[0]);
        const p2 = mapPointToPixels(d.points[1]);
        if (p1.x !== null && p1.y !== null && p2.x !== null && p2.y !== null) {
          const d1 = getDistanceToLine(x, y, p1.x, p1.y, p2.x, p1.y);
          const d2 = getDistanceToLine(x, y, p2.x, p1.y, p2.x, p2.y);
          const d3 = getDistanceToLine(x, y, p2.x, p2.y, p1.x, p2.y);
          const d4 = getDistanceToLine(x, y, p1.x, p2.y, p1.x, p1.y);
          if (Math.min(d1, d2, d3, d4) < 8) return d.id;
        }
      } else if (d.type === 'polyline' && d.points.length >= 2) {
        for (let i = 0; i < d.points.length - 1; i++) {
          const p1 = mapPointToPixels(d.points[i]);
          const p2 = mapPointToPixels(d.points[i + 1]);
          if (p1.x !== null && p1.y !== null && p2.x !== null && p2.y !== null) {
            const dist = getDistanceToLine(x, y, p1.x, p1.y, p2.x, p2.y);
            if (dist < 8) return d.id;
          }
        }
      }
    }
    return null;
  };

  // Handle drawing rendering on canvas
  useEffect(() => {
    if (!canvasRef.current || position.width === 0) return;
    const ctx = canvasRef.current.getContext('2d');
    if (!ctx) return;

    ctx.clearRect(0, 0, position.width, position.height);

    const drawItem = (
      type: string,
      points: Point[],
      color: string,
      lineWidth: number,
      fill: boolean,
      opacity: number,
      isTemp = false
    ) => {
      if (points.length === 0) return;

      const screenPts = points.map(mapPointToPixels);
      
      // If we are currently drawing, append the cursor position as a preview point
      if (isTemp && cursorPos && type !== 'polyline') {
        screenPts.push(mapPointToPixels(cursorPos));
      }

      ctx.strokeStyle = hexToRgba(color, opacity);
      ctx.lineWidth = lineWidth;
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';

      if (type === 'line' && screenPts.length >= 2) {
        const p1 = screenPts[0];
        const p2 = screenPts[1];
        if (p1.x !== null && p1.y !== null && p2.x !== null && p2.y !== null) {
          ctx.beginPath();
          ctx.moveTo(p1.x, p1.y);
          ctx.lineTo(p2.x, p2.y);
          ctx.stroke();
        }
      } else if (type === 'box' && screenPts.length >= 2) {
        const p1 = screenPts[0];
        const p2 = screenPts[1];
        if (p1.x !== null && p1.y !== null && p2.x !== null && p2.y !== null) {
          ctx.beginPath();
          ctx.rect(p1.x, p1.y, p2.x - p1.x, p2.y - p1.y);
          ctx.stroke();
          if (fill) {
            ctx.fillStyle = hexToRgba(color, opacity * 0.2); // Fill with translucent version
            ctx.fill();
          }
        }
      } else if (type === 'polyline' && screenPts.length >= 1) {
        ctx.beginPath();
        let started = false;
        screenPts.forEach((p) => {
          if (p.x !== null && p.y !== null) {
            if (!started) {
              ctx.moveTo(p.x, p.y);
              started = true;
            } else {
              ctx.lineTo(p.x, p.y);
            }
          }
        });

        // Drawing a line preview to current cursor position
        if (isTemp && cursorPos) {
          const cp = mapPointToPixels(cursorPos);
          if (cp.x !== null && cp.y !== null) {
            if (!started) {
              ctx.moveTo(cp.x, cp.y);
            } else {
              ctx.lineTo(cp.x, cp.y);
            }
          }
        }
        ctx.stroke();
      }
    };

    const drawSelectionHandles = (points: Point[], color: string) => {
      points.forEach((pt) => {
        const { x, y } = mapPointToPixels(pt);
        if (x !== null && y !== null) {
          ctx.beginPath();
          ctx.arc(x, y, 5, 0, 2 * Math.PI);
          ctx.fillStyle = '#ffffff';
          ctx.fill();
          ctx.strokeStyle = color;
          ctx.lineWidth = 2;
          ctx.stroke();
        }
      });
    };

    // Draw saved items
    drawings.forEach((d) => {
      drawItem(d.type, d.points, d.color, d.lineWidth, d.fill, d.opacity);
      if (d.id === selectedDrawingId) {
        drawSelectionHandles(d.points, d.color);
      }
    });

    // Draw active drawing in progress
    if (isDrawing && tempPoints.length > 0) {
      drawItem(
        activeTool === 'polyline' ? 'polyline' : activeTool,
        tempPoints,
        currentColor,
        currentLineWidth,
        fillBox,
        currentOpacity,
        true
      );
    }
  }, [drawings, isDrawing, tempPoints, cursorPos, position, rangeChangeKey, activeTool, currentColor, currentLineWidth, fillBox, currentOpacity, selectedDrawingId]);

  // Mouse Interaction handlers
  const handleMouseDown = (e: React.MouseEvent) => {
    console.log('DrawingOverlay: Mouse down event captured. Tool:', activeTool);
    
    if (activeTool === 'select') {
      if (!canvasRef.current) return;
      const rect = canvasRef.current.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      const targetId = findDrawingUnderCursor(x, y);
      setSelectedDrawingId(targetId);
      return;
    }

    const pt = mapPixelsToPoint(e.clientX, e.clientY);
    if (!pt) return;

    if (activeTool === 'eraser') {
      if (!canvasRef.current) return;
      const rect = canvasRef.current.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      const targetId = findDrawingUnderCursor(x, y);
      if (targetId) {
        setDrawings((prev) => prev.filter((d) => d.id !== targetId));
        if (selectedDrawingId === targetId) {
          setSelectedDrawingId(null);
        }
      }
      return;
    }

    if (activeTool === 'polyline') {
      if (!isDrawing) {
        setIsDrawing(true);
        setTempPoints([pt]);
      } else {
        setTempPoints((prev) => [...prev, pt]);
      }
    } else {
      // Line or Box
      setIsDrawing(true);
      setTempPoints([pt]);
    }
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (activeTool === 'select') return;

    const pt = mapPixelsToPoint(e.clientX, e.clientY);
    if (!pt) return;

    setCursorPos(pt);

    if (isDrawing && activeTool !== 'polyline') {
      // Update coordinates for preview
      if (tempPoints.length === 1) {
        setTempPoints([tempPoints[0], pt]);
      } else if (tempPoints.length === 2) {
        setTempPoints([tempPoints[0], pt]);
      }
    }
  };

  const handleMouseUp = () => {
    if (activeTool === 'select' || activeTool === 'polyline' || activeTool === 'eraser') return;

    if (isDrawing && tempPoints.length >= 2) {
      const newDrawing: Drawing = {
        id: `drawing_${Date.now()}`,
        type: activeTool as 'line' | 'box',
        points: [...tempPoints],
        color: currentColor,
        lineWidth: currentLineWidth,
        fill: fillBox,
        opacity: currentOpacity,
      };
      setDrawings((prev) => [...prev, newDrawing]);
      setIsDrawing(false);
      setTempPoints([]);
      setActiveTool('select'); // Automatically switch back to selection pointer
    }
  };

  const handleDoubleClick = () => {
    if (activeTool === 'polyline' && isDrawing && tempPoints.length >= 2) {
      const newDrawing: Drawing = {
        id: `drawing_${Date.now()}`,
        type: 'polyline',
        points: [...tempPoints],
        color: currentColor,
        lineWidth: currentLineWidth,
        fill: false, // Polyline has no fill
        opacity: currentOpacity,
      };
      setDrawings((prev) => [...prev, newDrawing]);
      setIsDrawing(false);
      setTempPoints([]);
      setActiveTool('select');
    }
  };

  // Listen to mousemove and mousedown on containerRef (using capture: true) to allow hover select/drag
  useEffect(() => {
    if (!containerRef.current) return;
    const container = containerRef.current;

    const handleContainerMouseMove = (e: MouseEvent) => {
      if (activeTool !== 'select' || !canvasRef.current) {
        setIsHoveringDrawing(false);
        return;
      }
      const rect = canvasRef.current.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;

      const hoveredId = findDrawingUnderCursor(x, y);
      setIsHoveringDrawing(hoveredId !== null);
    };

    const handleContainerMouseDown = (e: MouseEvent) => {
      if (activeTool !== 'select' || !canvasRef.current) return;
      const rect = canvasRef.current.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;

      const hoveredId = findDrawingUnderCursor(x, y);
      // If clicked outside any drawing, deselect
      if (hoveredId === null) {
        setSelectedDrawingId(null);
      }
    };

    container.addEventListener('mousemove', handleContainerMouseMove, true);
    container.addEventListener('mousedown', handleContainerMouseDown, true);

    return () => {
      container.removeEventListener('mousemove', handleContainerMouseMove, true);
      container.removeEventListener('mousedown', handleContainerMouseDown, true);
    };
  }, [containerRef, activeTool, drawings, rangeChangeKey, setSelectedDrawingId]);

  // Keyboard shortcut listener to cancel drawing (ESC) or delete selected drawing (Delete/Backspace)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setIsDrawing(false);
        setTempPoints([]);
        setActiveTool('select');
      } else if (e.key === 'Delete' || e.key === 'Backspace') {
        if (activeTool === 'select' && selectedDrawingId) {
          setDrawings((prev) => prev.filter((d) => d.id !== selectedDrawingId));
          setSelectedDrawingId(null);
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [setActiveTool, selectedDrawingId, activeTool, setDrawings, setSelectedDrawingId]);

  if (position.width === 0) return null;

  return (
    <canvas
      ref={canvasRef}
      width={position.width}
      height={position.height}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onDoubleClick={handleDoubleClick}
      style={{
        position: 'absolute',
        left: `${position.left}px`,
        top: `${position.top}px`,
        width: `${position.width}px`,
        height: `${position.height}px`,
        zIndex: 999999, // Render on top of the entire chart widget
        pointerEvents: activeTool === 'select' ? (isHoveringDrawing ? 'auto' : 'none') : 'auto',
        cursor: activeTool === 'select' ? (isHoveringDrawing ? 'pointer' : 'default') : 'crosshair',
      }}
    />
  );
}
