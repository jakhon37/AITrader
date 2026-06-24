import { useEffect, useMemo, useRef, useState } from 'react';
import type { IChartApi, ISeriesApi } from 'lightweight-charts';
import type { Drawing } from './drawingTypes';
import { getSettingsMenuPosition } from './drawingUtils';
import { drawItemOnCanvas, drawSelectionHandlesOnCanvas } from './drawingRenderer';
import { DrawingSettingsMenu } from './DrawingSettingsMenu';
import { useCanvasPosition, useDrawingInteractions } from './hooks';

interface DrawingOverlayProps {
  chart: IChartApi;
  candleSeries: ISeriesApi<'Candlestick'>;
  activeTool: 'select' | 'line' | 'box' | 'polyline' | 'eraser' | 'position' | 'fibonacci';
  setActiveTool: (tool: 'select' | 'line' | 'box' | 'polyline' | 'eraser' | 'position' | 'fibonacci') => void;
  drawings: Drawing[];
  setDrawings: React.Dispatch<React.SetStateAction<Drawing[]>>;
  containerRef: React.RefObject<HTMLDivElement | null>;
  currentColor: string;
  currentLineWidth: number;
  fillBox: boolean;
  currentOpacity: number;
  selectedDrawingId: string | null;
  setSelectedDrawingId: (id: string | null) => void;
  onUpdateColor: (color: string) => void;
  onUpdateLineWidth: (width: number) => void;
  onUpdateFill: (fill: boolean) => void;
  onUpdateOpacity: (opacity: number) => void;
  onUpdateExtendRight?: (extend: boolean) => void;
  onUpdateFibLevels?: (levels: number[]) => void;
  currentExtendRight?: boolean;
  currentFibLevels?: number[];
  entryLinePrice?: number | null;
  slLinePrice?: number | null;
  tpLinePrice?: number | null;
  onUpdateEntryPrice?: (price: number) => void;
  onUpdateSLPrice?: (price: number) => void;
  onUpdateTPPrice?: (price: number) => void;
  layoutKey?: number;
  onPositionInteractionChange?: (active: boolean) => void;
}

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
  onUpdateColor,
  onUpdateLineWidth,
  onUpdateFill,
  onUpdateOpacity,
  onUpdateExtendRight,
  onUpdateFibLevels,
  currentExtendRight = false,
  currentFibLevels,
  entryLinePrice,
  slLinePrice,
  tpLinePrice,
  onUpdateEntryPrice,
  onUpdateSLPrice,
  onUpdateTPPrice,
  layoutKey = 0,
  onPositionInteractionChange,
}: DrawingOverlayProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [rangeChangeKey, setRangeChangeKey] = useState(0);

  useEffect(() => {
    if (layoutKey > 0) setRangeChangeKey((prev) => prev + 1);
  }, [layoutKey]);

  // Hook 1: Layout alignment & Coordinate projection
  const { position, mapPointToPixels, mapPixelsToPoint, mapPixelToPrice, mapPriceToY } = useCanvasPosition(
    chart,
    candleSeries,
    containerRef,
    canvasRef
  );

  // Subscribe to chart zoom / scroll to repaint the canvas
  useEffect(() => {
    if (!chart) return;
    const handleRangeChange = () => setRangeChangeKey((prev) => prev + 1);
    chart.timeScale().subscribeVisibleLogicalRangeChange(handleRangeChange);
    return () => {
      try {
        chart.timeScale().unsubscribeVisibleLogicalRangeChange(handleRangeChange);
      } catch (err) {
        void err;
      }
    };
  }, [chart]);

  // Hook 2: User input gestures (drawing, dragging, selecting, deleting)
  const {
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
  } = useDrawingInteractions({
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
    mapPixelToPrice,
    mapPriceToY,
    currentExtendRight,
    currentFibLevels,
    entryLinePrice,
    slLinePrice,
    tpLinePrice,
    onUpdateEntryPrice,
    onUpdateSLPrice,
    onUpdateTPPrice,
  });

  const positionInteracting = useMemo(() => {
    if (activeTool === 'position' || (isDrawing && activeTool === 'position')) {
      return true;
    }
    if (dragState?.drawingId) {
      const d = drawings.find((item) => item.id === dragState.drawingId);
      if (d?.type === 'position') return true;
    }
    return false;
  }, [activeTool, isDrawing, dragState, drawings]);

  useEffect(() => {
    onPositionInteractionChange?.(positionInteracting);
  }, [positionInteracting, onPositionInteractionChange]);

  // Effect: Render drawings onto canvas
  useEffect(() => {
    if (!canvasRef.current || position.width === 0) return;
    const ctx = canvasRef.current.getContext('2d');
    if (!ctx) return;

    ctx.clearRect(0, 0, position.width, position.height);

    // Draw saved items
    drawings.forEach((d) => {
      drawItemOnCanvas(
        ctx,
        d.type,
        d.points,
        d.color,
        d.lineWidth,
        d.fill,
        d.opacity,
        mapPointToPixels,
        false,
        null,
        d.extendRight,
        d.fibLevels
      );
      if (d.id === selectedDrawingId) {
        drawSelectionHandlesOnCanvas(ctx, d.points, d.color, mapPointToPixels);
      }
    });

    // Draw active drawing in progress
    if (isDrawing && tempPoints.length > 0) {
      drawItemOnCanvas(
        ctx,
        activeTool === 'polyline' ? 'polyline' : activeTool,
        tempPoints,
        currentColor,
        currentLineWidth,
        fillBox,
        currentOpacity,
        mapPointToPixels,
        true,
        cursorPos,
        activeTool === 'fibonacci' ? currentExtendRight : false,
        activeTool === 'fibonacci' ? currentFibLevels : undefined
      );
    }

    // Helper to draw rounded rectangle for badges
    const drawRoundedRect = (c: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) => {
      c.beginPath();
      c.moveTo(x + r, y);
      c.lineTo(x + w - r, y);
      c.quadraticCurveTo(x + w, y, x + w, y + r);
      c.lineTo(x + w, y + h - r);
      c.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
      c.lineTo(x + r, y + h);
      c.quadraticCurveTo(x, y + h, x, y + h - r);
      c.lineTo(x, y + r);
      c.quadraticCurveTo(x, y, x + r, y);
      c.closePath();
    };

    // Draw active order lines (Limit Entry, Stop Loss, Take Profit)
    const drawOrderLine = (price: number, color: string, label: string) => {
      const y = candleSeries.priceToCoordinate(price);
      if (y === null) return;

      ctx.save();
      // Draw horizontal dashed line
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.5;
      ctx.setLineDash([6, 4]);
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(position.width, y);
      ctx.stroke();

      // Draw badge on the right
      ctx.setLineDash([]);
      const text = `${label}: ${price.toFixed(5)}`;
      ctx.font = 'bold 11px system-ui, -apple-system, sans-serif';
      const textWidth = ctx.measureText(text).width;
      const padX = 8;
      const padY = 4;
      const badgeW = textWidth + padX * 2;
      const badgeH = 18 + padY;
      const badgeX = position.width - badgeW - 12; // 12px margin from right price axis
      const badgeY = y - badgeH / 2;

      ctx.fillStyle = color;
      drawRoundedRect(ctx, badgeX, badgeY, badgeW, badgeH, 4);
      ctx.fill();

      // Subtle light border on badge
      ctx.strokeStyle = 'rgba(255,255,255,0.2)';
      ctx.lineWidth = 1;
      ctx.stroke();

      // Text color contrast check
      ctx.fillStyle = color === '#00e676' ? '#000000' : '#ffffff';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(text, badgeX + badgeW / 2, badgeY + badgeH / 2 + 0.5);
      ctx.restore();
    };

    if (entryLinePrice !== null && entryLinePrice !== undefined && entryLinePrice > 0) {
      drawOrderLine(entryLinePrice, '#2979ff', 'Limit Entry');
    }
    if (slLinePrice !== null && slLinePrice !== undefined && slLinePrice > 0) {
      drawOrderLine(slLinePrice, '#ff1744', 'Stop Loss');
    }
    if (tpLinePrice !== null && tpLinePrice !== undefined && tpLinePrice > 0) {
      drawOrderLine(tpLinePrice, '#00e676', 'Take Profit');
    }

  }, [drawings, isDrawing, tempPoints, cursorPos, position, rangeChangeKey, activeTool, currentColor, currentLineWidth, fillBox, currentOpacity, selectedDrawingId, mapPointToPixels, currentExtendRight, currentFibLevels, entryLinePrice, slLinePrice, tpLinePrice]);

  if (position.width === 0) return null;

  const hasOrderLines =
    (entryLinePrice != null && entryLinePrice > 0) ||
    (slLinePrice != null && slLinePrice > 0) ||
    (tpLinePrice != null && tpLinePrice > 0);

  const selectedDrawing = drawings.find((d) => d.id === selectedDrawingId);
  const menuPos = getSettingsMenuPosition(selectedDrawingId, drawings, mapPointToPixels, position.width);

  const orderLineActive =
    hoveredOrderLine !== null || (dragState?.type === 'order_line');

  return (
    <>
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
          pointerEvents: activeTool === 'select'
            ? (isHoveringDrawing || isHoveringHandle || orderLineActive || (hasOrderLines && dragState !== null) ? 'auto' : 'none')
            : 'auto',
          cursor: activeTool === 'select'
            ? (orderLineActive ? 'ns-resize' : (isHoveringHandle ? 'move' : (isHoveringDrawing ? 'pointer' : 'default')))
            : 'crosshair',
        }}
      />

      {activeTool === 'select' && selectedDrawing && menuPos && (
        <DrawingSettingsMenu
          selectedDrawing={selectedDrawing}
          position={menuPos}
          onUpdateColor={onUpdateColor}
          onUpdateLineWidth={onUpdateLineWidth}
          onUpdateFill={onUpdateFill}
          onUpdateOpacity={onUpdateOpacity}
          onUpdateExtendRight={onUpdateExtendRight}
          onUpdateFibLevels={onUpdateFibLevels}
          onDelete={() => {
            setDrawings((prev) => prev.filter((d) => d.id !== selectedDrawingId));
            setSelectedDrawingId(null);
          }}
        />
      )}
    </>
  );
}
