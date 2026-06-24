import { useEffect, useRef, useState } from 'react';
import { useLightweightChart, useChartDataStream } from './hooks';
import { DrawingToolbar } from './DrawingToolbar';
import { DrawingOverlay } from './DrawingOverlay';
import type { Drawing } from './drawingTypes';

interface Props {
  instrument: string;
  timeframe: string;
  onNewBar?: (bar: { time: number; open: number; high: number; low: number; close: number; volume: number }) => void;
  virtualEndTime?: string; // ISO string representing active replay timestamp
  entryLinePrice?: number | null;
  slLinePrice?: number | null;
  tpLinePrice?: number | null;
  onPositionSelect?: (position: { entry: number; sl: number; tp: number } | null) => void;
  onUpdateEntryPrice?: (price: number) => void;
  onUpdateSLPrice?: (price: number) => void;
  onUpdateTPPrice?: (price: number) => void;
  /** Increment to clear position-tool drafts from the chart after order execution. */
  orderDraftKey?: number;
}

export function CandleChart({
  instrument,
  timeframe,
  onNewBar,
  virtualEndTime,
  entryLinePrice,
  slLinePrice,
  tpLinePrice,
  onPositionSelect,
  onUpdateEntryPrice,
  onUpdateSLPrice,
  onUpdateTPPrice,
  orderDraftKey = 0,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [activeTool, setActiveTool] = useState<'select' | 'line' | 'box' | 'polyline' | 'eraser' | 'position' | 'fibonacci'>('select');
  const [drawings, setDrawings] = useState<Drawing[]>([]);
  const [selectedDrawingId, setSelectedDrawingId] = useState<string | null>(null);

  const [toolSettings, setToolSettings] = useState<Record<string, {
    color: string;
    lineWidth: number;
    fill: boolean;
    opacity: number;
    extendRight?: boolean;
    fibLevels?: number[];
  }>>({
    line: { color: '#00e5ff', lineWidth: 2, fill: false, opacity: 0.8 },
    box: { color: '#00e676', lineWidth: 2, fill: true, opacity: 0.8 },
    polyline: { color: '#ff9100', lineWidth: 2, fill: false, opacity: 0.8 },
    position: { color: '#00e676', lineWidth: 2, fill: true, opacity: 0.8 },
    fibonacci: {
      color: '#ffea00',
      lineWidth: 1.5,
      fill: true,
      opacity: 0.8,
      extendRight: false,
      fibLevels: [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0, 1.618, 2.618, 3.618, 4.236],
    },
  });

  const handleSetActiveTool = (tool: 'select' | 'line' | 'box' | 'polyline' | 'eraser' | 'position' | 'fibonacci') => {
    setActiveTool(tool);
    setSelectedDrawingId(null);
  };

  // Determine active target settings
  const selectedDrawing = drawings.find((d) => d.id === selectedDrawingId);
  const targetToolType = selectedDrawing ? selectedDrawing.type : (activeTool === 'select' || activeTool === 'eraser' ? 'line' : activeTool);

  const currentColor = selectedDrawing ? selectedDrawing.color : (toolSettings[targetToolType]?.color || '#00e5ff');
  const currentLineWidth = selectedDrawing ? selectedDrawing.lineWidth : (toolSettings[targetToolType]?.lineWidth || 2);
  const fillBox = selectedDrawing ? selectedDrawing.fill : (toolSettings[targetToolType]?.fill ?? true);
  const currentOpacity = selectedDrawing ? selectedDrawing.opacity : (toolSettings[targetToolType]?.opacity || 0.8);
  const currentExtendRight = selectedDrawing ? selectedDrawing.extendRight : (toolSettings[targetToolType]?.extendRight ?? false);
  const currentFibLevels = selectedDrawing ? selectedDrawing.fibLevels : (toolSettings[targetToolType]?.fibLevels ?? [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]);

  const setCurrentColor = (color: string) => {
    if (selectedDrawingId) {
      setDrawings((prev) => prev.map((d) => d.id === selectedDrawingId ? { ...d, color } : d));
      if (selectedDrawing) {
        setToolSettings((prev) => ({
          ...prev,
          [selectedDrawing.type]: { ...prev[selectedDrawing.type], color },
        }));
      }
    } else {
      setToolSettings((prev) => ({
        ...prev,
        [targetToolType]: { ...prev[targetToolType], color },
      }));
    }
  };

  const setCurrentLineWidth = (lineWidth: number) => {
    if (selectedDrawingId) {
      setDrawings((prev) => prev.map((d) => d.id === selectedDrawingId ? { ...d, lineWidth } : d));
      if (selectedDrawing) {
        setToolSettings((prev) => ({
          ...prev,
          [selectedDrawing.type]: { ...prev[selectedDrawing.type], lineWidth },
        }));
      }
    } else {
      setToolSettings((prev) => ({
        ...prev,
        [targetToolType]: { ...prev[targetToolType], lineWidth },
      }));
    }
  };

  const setFillBox = (fill: boolean) => {
    if (selectedDrawingId) {
      setDrawings((prev) => prev.map((d) => d.id === selectedDrawingId ? { ...d, fill } : d));
      if (selectedDrawing) {
        setToolSettings((prev) => ({
          ...prev,
          [selectedDrawing.type]: { ...prev[selectedDrawing.type], fill },
        }));
      }
    } else {
      setToolSettings((prev) => ({
        ...prev,
        [targetToolType]: { ...prev[targetToolType], fill },
      }));
    }
  };

  const setCurrentOpacity = (opacity: number) => {
    if (selectedDrawingId) {
      setDrawings((prev) => prev.map((d) => d.id === selectedDrawingId ? { ...d, opacity } : d));
      if (selectedDrawing) {
        setToolSettings((prev) => ({
          ...prev,
          [selectedDrawing.type]: { ...prev[selectedDrawing.type], opacity },
        }));
      }
    } else {
      setToolSettings((prev) => ({
        ...prev,
        [targetToolType]: { ...prev[targetToolType], opacity },
      }));
    }
  };

  const setExtendRight = (extend: boolean) => {
    if (selectedDrawingId) {
      setDrawings((prev) => prev.map((d) => d.id === selectedDrawingId ? { ...d, extendRight: extend } : d));
      if (selectedDrawing) {
        setToolSettings((prev) => ({
          ...prev,
          [selectedDrawing.type]: { ...prev[selectedDrawing.type], extendRight: extend },
        }));
      }
    } else {
      setToolSettings((prev) => ({
        ...prev,
        [targetToolType]: { ...prev[targetToolType], extendRight: extend },
      }));
    }
  };

  const setFibLevels = (levels: number[]) => {
    if (selectedDrawingId) {
      setDrawings((prev) => prev.map((d) => d.id === selectedDrawingId ? { ...d, fibLevels: levels } : d));
      if (selectedDrawing) {
        setToolSettings((prev) => ({
          ...prev,
          [selectedDrawing.type]: { ...prev[selectedDrawing.type], fibLevels: levels },
        }));
      }
    } else {
      setToolSettings((prev) => ({
        ...prev,
        [targetToolType]: { ...prev[targetToolType], fibLevels: levels },
      }));
    }
  };
  
  // Custom hook to initialize lightweight-chart canvas and series, and handle resize observer
  const { chart, candleSeries, volumeSeries } = useLightweightChart(containerRef);

  // Custom hook to handle initial fetch, pagination, window scroll events, and websocket/replay feeds
  useChartDataStream(chart, candleSeries, volumeSeries, {
    instrument,
    timeframe,
    onNewBar,
    virtualEndTime,
  });

  // Clear position-tool drawings when parent signals order draft was executed
  useEffect(() => {
    if (orderDraftKey === 0) return;
    setDrawings((prev) => prev.filter((d) => d.type !== 'position'));
    setSelectedDrawingId(null);
  }, [orderDraftKey]);

  // Trigger onPositionSelect callback when active position drawing is selected or modified
  useEffect(() => {
    if (!onPositionSelect) return;
    if (selectedDrawingId) {
      const selected = drawings.find((d) => d.id === selectedDrawingId);
      if (selected && selected.type === 'position' && selected.points.length >= 3) {
        onPositionSelect({
          entry: selected.points[0].price,
          tp: selected.points[1].price,
          sl: selected.points[2].price,
        });
        return;
      }
    }
    onPositionSelect(null);
  }, [selectedDrawingId, drawings, onPositionSelect]);

  const clearDrawings = () => {
    setDrawings([]);
    setSelectedDrawingId(null);
  };

  return (
    <div style={{ display: 'flex', width: '100%', height: '100%', position: 'relative' }}>
      {/* Drawing Toolbar */}
      <DrawingToolbar
        activeTool={activeTool}
        setActiveTool={handleSetActiveTool}
        onClear={clearDrawings}
      />

      {/* Chart container */}
      <div style={{ flex: 1, position: 'relative', height: '100%' }}>
        <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
        {chart && candleSeries && (
          <DrawingOverlay
            chart={chart}
            candleSeries={candleSeries}
            activeTool={activeTool}
            setActiveTool={handleSetActiveTool}
            drawings={drawings}
            setDrawings={setDrawings}
            containerRef={containerRef}
            currentColor={currentColor}
            currentLineWidth={currentLineWidth}
            fillBox={fillBox}
            currentOpacity={currentOpacity}
            selectedDrawingId={selectedDrawingId}
            setSelectedDrawingId={setSelectedDrawingId}
            onUpdateColor={setCurrentColor}
            onUpdateLineWidth={setCurrentLineWidth}
            onUpdateFill={setFillBox}
            onUpdateOpacity={setCurrentOpacity}
            currentExtendRight={currentExtendRight}
            currentFibLevels={currentFibLevels}
            onUpdateExtendRight={setExtendRight}
            onUpdateFibLevels={setFibLevels}
            entryLinePrice={entryLinePrice}
            slLinePrice={slLinePrice}
            tpLinePrice={tpLinePrice}
            onUpdateEntryPrice={onUpdateEntryPrice}
            onUpdateSLPrice={onUpdateSLPrice}
            onUpdateTPPrice={onUpdateTPPrice}
          />
        )}
      </div>
    </div>
  );
}
