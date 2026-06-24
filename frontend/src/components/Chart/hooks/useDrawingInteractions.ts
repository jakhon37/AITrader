import { useEffect, useState } from 'react';
import type { Point, Drawing, DragState } from '../drawingTypes';
import { findDrawingUnderCursor, isNearAnyHandle } from '../drawingUtils';

interface Props {
  activeTool: 'select' | 'line' | 'box' | 'polyline' | 'eraser' | 'position' | 'fibonacci';
  setActiveTool: (tool: 'select' | 'line' | 'box' | 'polyline' | 'eraser' | 'position' | 'fibonacci') => void;
  drawings: Drawing[];
  setDrawings: React.Dispatch<React.SetStateAction<Drawing[]>>;
  selectedDrawingId: string | null;
  setSelectedDrawingId: (id: string | null) => void;
  currentColor: string;
  currentLineWidth: number;
  fillBox: boolean;
  currentOpacity: number;
  canvasRef: React.RefObject<HTMLCanvasElement | null>;
  containerRef: React.RefObject<HTMLDivElement | null>;
  rangeChangeKey: number;
  mapPixelsToPoint: (clientX: number, clientY: number) => Point | null;
  mapPointToPixels: (pt: Point) => { x: number | null; y: number | null };
  currentExtendRight?: boolean;
  currentFibLevels?: number[];
  entryLinePrice?: number | null;
  slLinePrice?: number | null;
  tpLinePrice?: number | null;
  onUpdateEntryPrice?: (price: number) => void;
  onUpdateSLPrice?: (price: number) => void;
  onUpdateTPPrice?: (price: number) => void;
}

export function useDrawingInteractions({
  activeTool,
  setActiveTool,
  drawings,
  setDrawings,
  selectedDrawingId,
  setSelectedDrawingId,
  currentColor,
  currentLineWidth,
  fillBox,
  currentOpacity,
  canvasRef,
  containerRef,
  rangeChangeKey,
  mapPixelsToPoint,
  mapPointToPixels,
  currentExtendRight = false,
  currentFibLevels = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0, 1.618, 2.618, 3.618, 4.236],
  entryLinePrice,
  slLinePrice,
  tpLinePrice,
  onUpdateEntryPrice,
  onUpdateSLPrice,
  onUpdateTPPrice,
}: Props) {
  const [isDrawing, setIsDrawing] = useState(false);
  const [tempPoints, setTempPoints] = useState<Point[]>([]);
  const [cursorPos, setCursorPos] = useState<Point | null>(null);
  const [isHoveringDrawing, setIsHoveringDrawing] = useState(false);
  const [isHoveringHandle, setIsHoveringHandle] = useState(false);
  const [hoveredOrderLine, setHoveredOrderLine] = useState<'entry' | 'sl' | 'tp' | null>(null);
  const [dragState, setDragState] = useState<DragState | null>(null);

  const getOrderLinesY = () => {
    const entryY = (entryLinePrice !== null && entryLinePrice !== undefined)
      ? mapPointToPixels({ time: 0, price: entryLinePrice }).y
      : null;
    const slY = (slLinePrice !== null && slLinePrice !== undefined)
      ? mapPointToPixels({ time: 0, price: slLinePrice }).y
      : null;
    const tpY = (tpLinePrice !== null && tpLinePrice !== undefined)
      ? mapPointToPixels({ time: 0, price: tpLinePrice }).y
      : null;
    return { entryY, slY, tpY };
  };

  const checkNearOrderLine = (y: number) => {
    const { entryY, slY, tpY } = getOrderLinesY();
    let closest: 'entry' | 'sl' | 'tp' | null = null;
    let minDiff = 8; // 8px threshold

    if (entryY !== null) {
      const diff = Math.abs(y - entryY);
      if (diff < minDiff) {
        minDiff = diff;
        closest = 'entry';
      }
    }
    if (slY !== null) {
      const diff = Math.abs(y - slY);
      if (diff < minDiff) {
        minDiff = diff;
        closest = 'sl';
      }
    }
    if (tpY !== null) {
      const diff = Math.abs(y - tpY);
      if (diff < minDiff) {
        minDiff = diff;
        closest = 'tp';
      }
    }
    return closest;
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    if (activeTool === 'select') {
      if (!canvasRef.current) return;
      const rect = canvasRef.current.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;

      const clickedOrderLine = checkNearOrderLine(y);
      if (clickedOrderLine) {
        setDragState({
          type: 'order_line',
          drawingId: clickedOrderLine,
        });
        return;
      }

      let clickedHandleIndex = -1;
      if (selectedDrawingId) {
        const drawing = drawings.find((d) => d.id === selectedDrawingId);
        if (drawing) {
          for (let i = 0; i < drawing.points.length; i++) {
            const { x: hx, y: hy } = mapPointToPixels(drawing.points[i]);
            if (hx !== null && hy !== null) {
              const dx = x - hx;
              const dy = y - hy;
              if (Math.sqrt(dx * dx + dy * dy) < 8) {
                clickedHandleIndex = i;
                break;
              }
            }
          }
        }
      }

      if (clickedHandleIndex !== -1) {
        setDragState({
          type: 'handle',
          drawingId: selectedDrawingId!,
          pointIndex: clickedHandleIndex,
        });
        return;
      }

      const targetId = findDrawingUnderCursor(x, y, drawings, mapPointToPixels, canvasRef.current?.width || 0);
      if (targetId) {
        setSelectedDrawingId(targetId);
        const clickPt = mapPixelsToPoint(e.clientX, e.clientY);
        if (clickPt) {
          setDragState({
            type: 'body',
            drawingId: targetId,
            startMousePoint: clickPt,
            startDrawingPoints: drawings.find((d) => d.id === targetId)!.points,
          });
        }
      } else {
        setSelectedDrawingId(null);
      }
      return;
    }

    const pt = mapPixelsToPoint(e.clientX, e.clientY);
    if (!pt) return;

    if (activeTool === 'eraser') {
      if (!canvasRef.current) return;
      const rect = canvasRef.current.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      const targetId = findDrawingUnderCursor(x, y, drawings, mapPointToPixels, canvasRef.current?.width || 0);
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
      setIsDrawing(true);
      setTempPoints([pt]);
    }
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    const pt = mapPixelsToPoint(e.clientX, e.clientY);
    if (!pt) return;

    setCursorPos(pt);

    if (activeTool === 'select') {
      if (dragState) {
        if (dragState.type === 'order_line') {
          const clickPt = mapPixelsToPoint(e.clientX, e.clientY);
          if (clickPt) {
            const price = clickPt.price;
            if (dragState.drawingId === 'entry' && onUpdateEntryPrice) {
              onUpdateEntryPrice(price);
            } else if (dragState.drawingId === 'sl' && onUpdateSLPrice) {
              onUpdateSLPrice(price);
            } else if (dragState.drawingId === 'tp' && onUpdateTPPrice) {
              onUpdateTPPrice(price);
            }
          }
          return;
        }

        if (dragState.type === 'handle' && dragState.pointIndex !== undefined) {
          setDrawings((prev) =>
            prev.map((d) => {
              if (d.id === dragState.drawingId) {
                const newPoints = [...d.points];
                newPoints[dragState.pointIndex!] = pt;
                if (d.type === 'position') {
                  if (dragState.pointIndex === 1) {
                    newPoints[2] = { ...newPoints[2], time: pt.time };
                  } else if (dragState.pointIndex === 2) {
                    newPoints[1] = { ...newPoints[1], time: pt.time };
                  }
                }
                return { ...d, points: newPoints };
              }
              return d;
            })
          );
        } else if (dragState.type === 'body' && dragState.startMousePoint && dragState.startDrawingPoints) {
          const deltaPrice = pt.price - dragState.startMousePoint.price;
          const deltaTime = pt.time - dragState.startMousePoint.time;

          setDrawings((prev) =>
            prev.map((d) => {
              if (d.id === dragState.drawingId) {
                const newPoints = dragState.startDrawingPoints!.map((origPt) => ({
                  time: origPt.time + deltaTime,
                  price: origPt.price + deltaPrice,
                }));
                return { ...d, points: newPoints };
              }
              return d;
            })
          );
        }
      }
      return;
    }

    if (isDrawing) {
      if (activeTool === 'position') {
        const p0 = tempPoints[0];
        const isLong = pt.price < p0.price; // going down on chart means stop loss goes down, take profit goes up
        
        let targetPrice: number;
        const stopPrice = pt.price;

        if (isLong) {
          const stopDist = p0.price - stopPrice;
          targetPrice = p0.price + 3 * stopDist;
        } else {
          const stopDist = stopPrice - p0.price;
          targetPrice = p0.price - 3 * stopDist;
        }

        setTempPoints([
          p0,
          { time: pt.time, price: targetPrice },
          { time: pt.time, price: stopPrice },
        ]);
      } else if (activeTool !== 'polyline') {
        if (tempPoints.length === 1) {
          setTempPoints([tempPoints[0], pt]);
        } else if (tempPoints.length === 2) {
          setTempPoints([tempPoints[0], pt]);
        }
      }
    }
  };

  const handleMouseUp = () => {
    if (activeTool === 'select') {
      setDragState(null);
      return;
    }

    if (activeTool === 'polyline') {
      return; // Do not finalize polyline on mouse up! Let it continue drawing.
    }

    if (isDrawing && tempPoints.length >= 2) {
      const newId = `drawing_${Date.now()}`;
      const newDrawing: Drawing = {
        id: newId,
        type: activeTool as Drawing['type'],
        points: [...tempPoints],
        color: currentColor,
        lineWidth: currentLineWidth,
        fill: fillBox,
        opacity: currentOpacity,
        extendRight: activeTool === 'fibonacci' ? currentExtendRight : undefined,
        fibLevels: activeTool === 'fibonacci' ? currentFibLevels : undefined,
      };
      setDrawings((prev) => [...prev, newDrawing]);
      setIsDrawing(false);
      setTempPoints([]);
      setActiveTool('select');
      setSelectedDrawingId(newId);
    }
  };

  const handleDoubleClick = () => {
    if (activeTool === 'polyline' && isDrawing && tempPoints.length >= 2) {
      const pts = [...tempPoints];
      if (pts.length >= 2) {
        const last = pts[pts.length - 1];
        const prev = pts[pts.length - 2];
        if (last.time === prev.time && last.price === prev.price) {
          pts.pop();
        }
      }

      const newId = `drawing_${Date.now()}`;
      const newDrawing: Drawing = {
        id: newId,
        type: 'polyline',
        points: pts,
        color: currentColor,
        lineWidth: currentLineWidth,
        fill: false,
        opacity: currentOpacity,
      };
      setDrawings((prev) => [...prev, newDrawing]);
      setIsDrawing(false);
      setTempPoints([]);
      setActiveTool('select');
      setSelectedDrawingId(newId);
    }
  };

  useEffect(() => {
    if (!containerRef.current) return;
    const container = containerRef.current;

    const handleContainerMouseMove = (e: MouseEvent) => {
      if (activeTool !== 'select' || !canvasRef.current) {
        setIsHoveringDrawing(false);
        setIsHoveringHandle(false);
        setHoveredOrderLine(null);
        return;
      }
      const rect = canvasRef.current.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;

      const nearOrderLine = checkNearOrderLine(y);
      setHoveredOrderLine(nearOrderLine);

      if (nearOrderLine) {
        setIsHoveringDrawing(false);
        setIsHoveringHandle(false);
        return;
      }

      const hoveredId = findDrawingUnderCursor(x, y, drawings, mapPointToPixels, canvasRef.current?.width || 0);
      const nearHandle = isNearAnyHandle(x, y, selectedDrawingId, drawings, mapPointToPixels);
      setIsHoveringDrawing(hoveredId !== null);
      setIsHoveringHandle(nearHandle);
    };

    const handleContainerMouseDown = (e: MouseEvent) => {
      if (activeTool !== 'select' || !canvasRef.current) return;
      const rect = canvasRef.current.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;

      const nearOrderLine = checkNearOrderLine(y);
      if (nearOrderLine) return; // do not deselect drawings when clicking order lines

      const hoveredId = findDrawingUnderCursor(x, y, drawings, mapPointToPixels, canvasRef.current?.width || 0);
      const nearHandle = isNearAnyHandle(x, y, selectedDrawingId, drawings, mapPointToPixels);
      if (hoveredId === null && !nearHandle) {
        setSelectedDrawingId(null);
      }
    };

    container.addEventListener('mousemove', handleContainerMouseMove, true);
    container.addEventListener('mousedown', handleContainerMouseDown, true);

    return () => {
      container.removeEventListener('mousemove', handleContainerMouseMove, true);
      container.removeEventListener('mousedown', handleContainerMouseDown, true);
    };
  }, [containerRef, activeTool, drawings, rangeChangeKey, setSelectedDrawingId, selectedDrawingId, mapPointToPixels, canvasRef, entryLinePrice, slLinePrice, tpLinePrice]);

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

  return {
    isDrawing,
    tempPoints,
    cursorPos,
    isHoveringDrawing,
    isHoveringHandle,
    hoveredOrderLine,
    dragState,
    handleMouseDown,
    handleMouseMove,
    handleMouseUp,
    handleDoubleClick,
  };
}
