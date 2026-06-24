import type { Point, Drawing } from './drawingTypes';

// Convert hex color + opacity value to standard RGBA string
export const hexToRgba = (hex: string, alpha: number): string => {
  if (hex.startsWith('rgba') || hex.startsWith('var')) return hex;
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
};

// Distance formula for line segment
export const getDistanceToLine = (x: number, y: number, x1: number, y1: number, x2: number, y2: number): number => {
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

// Find which drawing is under the cursor
export const findDrawingUnderCursor = (
  x: number,
  y: number,
  drawings: Drawing[],
  mapPointToPixels: (pt: Point) => { x: number | null; y: number | null },
  canvasWidth: number
): string | null => {
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
    } else if (d.type === 'position' && d.points.length >= 3) {
      const p0 = mapPointToPixels(d.points[0]);
      const p1 = mapPointToPixels(d.points[1]);
      const p2 = mapPointToPixels(d.points[2]);
      if (p0.x !== null && p0.y !== null && p1.x !== null && p1.y !== null && p2.x !== null && p2.y !== null) {
        const left = Math.min(p0.x, p1.x);
        const right = Math.max(p0.x, p1.x);
        if (x >= left - 4 && x <= right + 4) {
          const targetMin = Math.min(p0.y, p1.y);
          const targetMax = Math.max(p0.y, p1.y);
          if (y >= targetMin && y <= targetMax) return d.id;
          const stopMin = Math.min(p0.y, p2.y);
          const stopMax = Math.max(p0.y, p2.y);
          if (y >= stopMin && y <= stopMax) return d.id;
        }
      }
    } else if (d.type === 'fibonacci' && d.points.length >= 2) {
      const p0 = mapPointToPixels(d.points[0]);
      const p1 = mapPointToPixels(d.points[1]);
      if (p0.x !== null && p0.y !== null && p1.x !== null && p1.y !== null) {
        if (getDistanceToLine(x, y, p0.x, p0.y, p1.x, p1.y) < 8) return d.id;
        const left = Math.min(p0.x, p1.x);
        const right = d.extendRight ? canvasWidth : Math.max(p0.x, p1.x);
        if (x >= left - 4 && x <= right + 4) {
          const ratios = d.fibLevels || [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0];
          for (const r of ratios) {
            const levelPrice = d.points[1].price - r * (d.points[1].price - d.points[0].price);
            const levelY = mapPointToPixels({ time: d.points[0].time, price: levelPrice }).y;
            if (levelY !== null && Math.abs(y - levelY) < 8) {
              return d.id;
            }
          }
        }
      }
    }
  }
  return null;
};

// Check if mouse is near any selection handle of the selected drawing
export const isNearAnyHandle = (
  x: number,
  y: number,
  selectedDrawingId: string | null,
  drawings: Drawing[],
  mapPointToPixels: (pt: Point) => { x: number | null; y: number | null }
): boolean => {
  if (!selectedDrawingId) return false;
  const drawing = drawings.find((d) => d.id === selectedDrawingId);
  if (!drawing) return false;
  for (const pt of drawing.points) {
    const p = mapPointToPixels(pt);
    if (p.x !== null && p.y !== null) {
      const dx = x - p.x;
      const dy = y - p.y;
      if (Math.sqrt(dx * dx + dy * dy) < 8) {
        return true;
      }
    }
  }
  return false;
};

export type SettingsMenuPlacement = 'above' | 'below';
export type DropdownDirection = 'up' | 'down';

const MENU_BAR_HEIGHT = 40;
const DROPDOWN_MAX_HEIGHT = 170;
const MENU_EDGE_MARGIN = 10;

// Calculate coordinates for floating settings menu
export const getSettingsMenuPosition = (
  selectedDrawingId: string | null,
  drawings: Drawing[],
  mapPointToPixels: (pt: Point) => { x: number | null; y: number | null },
  canvasWidth: number,
  canvasHeight: number,
): { top: number; left: number; placement: SettingsMenuPlacement; dropdownDirection: DropdownDirection } | null => {
  if (!selectedDrawingId) return null;
  const drawing = drawings.find((d) => d.id === selectedDrawingId);
  if (!drawing || drawing.points.length === 0) return null;

  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;

  drawing.points.forEach((pt) => {
    const { x, y } = mapPointToPixels(pt);
    if (x !== null && y !== null) {
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
    }
  });

  if (minX === Infinity || minY === Infinity) return null;

  const spaceAbove = minY - MENU_EDGE_MARGIN;
  const spaceBelow = canvasHeight - maxY - MENU_EDGE_MARGIN;
  const minAbove = MENU_BAR_HEIGHT + DROPDOWN_MAX_HEIGHT;
  const minBelow = MENU_BAR_HEIGHT + 8;

  let placement: SettingsMenuPlacement;
  if (spaceAbove >= minAbove && spaceAbove >= spaceBelow) {
    placement = 'above';
  } else if (spaceBelow >= minBelow) {
    placement = 'below';
  } else if (spaceBelow >= spaceAbove) {
    placement = 'below';
  } else {
    placement = 'above';
  }

  const top =
    placement === 'above'
      ? Math.max(MENU_EDGE_MARGIN, minY - MENU_BAR_HEIGHT - 8)
      : Math.min(canvasHeight - MENU_BAR_HEIGHT - MENU_EDGE_MARGIN, maxY + 8);

  const left = Math.max(10, Math.min(canvasWidth - 320, (minX + maxX) / 2 - 160));

  const spaceAboveMenu = top - MENU_EDGE_MARGIN;
  const spaceBelowMenu = canvasHeight - top - MENU_BAR_HEIGHT - MENU_EDGE_MARGIN;
  const dropdownDirection: DropdownDirection =
    spaceAboveMenu >= DROPDOWN_MAX_HEIGHT && spaceAboveMenu >= spaceBelowMenu ? 'up' : 'down';

  return { top, left, placement, dropdownDirection };
};
