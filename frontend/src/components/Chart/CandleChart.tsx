import { useRef, useState } from 'react';
import { useLightweightChart, useChartDataStream } from './hooks';
import { DrawingToolbar } from './DrawingToolbar';
import { DrawingOverlay } from './DrawingOverlay';

interface Props {
  instrument: string;
  timeframe: string;
  onNewBar?: (bar: { time: number; open: number; high: number; low: number; close: number; volume: number }) => void;
  virtualEndTime?: string; // ISO string representing active replay timestamp
}

export function CandleChart({ instrument, timeframe, onNewBar, virtualEndTime }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [activeTool, setActiveTool] = useState<'select' | 'line' | 'box' | 'polyline' | 'eraser'>('select');
  const [drawings, setDrawings] = useState<any[]>([]);
  const [selectedDrawingId, setSelectedDrawingId] = useState<string | null>(null);

  const [toolSettings, setToolSettings] = useState<Record<string, { color: string; lineWidth: number; fill: boolean; opacity: number }>>({
    line: { color: '#00e5ff', lineWidth: 2, fill: false, opacity: 0.8 },
    box: { color: '#00e676', lineWidth: 2, fill: true, opacity: 0.8 },
    polyline: { color: '#ff9100', lineWidth: 2, fill: false, opacity: 0.8 },
  });

  const handleSetActiveTool = (tool: 'select' | 'line' | 'box' | 'polyline' | 'eraser') => {
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
  
  // Custom hook to initialize lightweight-chart canvas and series, and handle resize observer
  const { chart, candleSeries, volumeSeries } = useLightweightChart(containerRef);

  // Custom hook to handle initial fetch, pagination, window scroll events, and websocket/replay feeds
  useChartDataStream(chart, candleSeries, volumeSeries, {
    instrument,
    timeframe,
    onNewBar,
    virtualEndTime,
  });

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
        currentColor={currentColor}
        setCurrentColor={setCurrentColor}
        currentLineWidth={currentLineWidth}
        setCurrentLineWidth={setCurrentLineWidth}
        fillBox={fillBox}
        setFillBox={setFillBox}
        currentOpacity={currentOpacity}
        setCurrentOpacity={setCurrentOpacity}
        showFillOption={targetToolType === 'box'}
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
          />
        )}
      </div>
    </div>
  );
}
