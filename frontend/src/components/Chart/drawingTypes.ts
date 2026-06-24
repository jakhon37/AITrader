export interface Point {
  time: number;
  price: number;
}

export interface Drawing {
  id: string;
  type: 'line' | 'box' | 'polyline' | 'position' | 'fibonacci';
  points: Point[];
  color: string;
  lineWidth: number;
  fill: boolean;
  opacity: number;
  extendRight?: boolean;
  fibLevels?: number[];
}

export interface DragState {
  type: 'handle' | 'body' | 'order_line';
  drawingId: string;
  pointIndex?: number;
  startMousePoint?: Point;
  startDrawingPoints?: Point[];
}
