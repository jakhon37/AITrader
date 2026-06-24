import type { Point } from './drawingTypes';
import { hexToRgba } from './drawingUtils';

export const drawItemOnCanvas = (
  ctx: CanvasRenderingContext2D,
  type: string,
  points: Point[],
  color: string,
  lineWidth: number,
  fill: boolean,
  opacity: number,
  mapPointToPixels: (pt: Point) => { x: number | null; y: number | null },
  isTemp = false,
  cursorPos: Point | null = null,
  extendRight = false,
  fibLevels?: number[]
) => {
  if (points.length === 0) return;

  const screenPts = points.map(mapPointToPixels);
  
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
        ctx.fillStyle = hexToRgba(color, opacity * 0.2);
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
  } else if (type === 'position' && screenPts.length >= 3) {
    if (points.length < 3) return;
    const p0 = screenPts[0];
    const p1 = screenPts[1];
    const p2 = screenPts[2];
    if (p0.x !== null && p0.y !== null && p1.x !== null && p1.y !== null && p2.x !== null && p2.y !== null) {
      const leftX = p0.x;
      const rightX = p1.x;

      // Target Zone (defined by p1) is Green
      ctx.fillStyle = 'rgba(0, 230, 118, 0.18)';
      ctx.strokeStyle = hexToRgba('#00e676', opacity);
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.rect(leftX, p0.y, rightX - leftX, p1.y - p0.y);
      ctx.fill();
      ctx.stroke();

      // Stop Loss Zone (defined by p2) is Red
      ctx.fillStyle = 'rgba(255, 23, 68, 0.18)';
      ctx.strokeStyle = hexToRgba('#ff1744', opacity);
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.rect(leftX, p0.y, rightX - leftX, p2.y - p0.y);
      ctx.fill();
      ctx.stroke();

      // Center entry line
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.5)';
      ctx.lineWidth = 1.5;
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(leftX, p0.y);
      ctx.lineTo(rightX, p0.y);
      ctx.stroke();
      ctx.setLineDash([]);

      const targetDiff = Math.abs(points[1].price - points[0].price);
      const stopDiff = Math.abs(points[0].price - points[2].price);
      const rrRatio = stopDiff !== 0 ? (targetDiff / stopDiff).toFixed(2) : '0.00';
      
      const isLong = points[1].price > points[0].price;
      const targetPctVal = ((points[1].price - points[0].price) / points[0].price) * 100;
      const stopPctVal = ((points[2].price - points[0].price) / points[0].price) * 100;

      const targetPctText = isLong ? `+${targetPctVal.toFixed(2)}%` : `${targetPctVal.toFixed(2)}%`;
      const stopPctText = isLong ? `${stopPctVal.toFixed(2)}%` : `+${stopPctVal.toFixed(2)}%`;

      const infoText = `R:R ${rrRatio} | Target ${targetPctText} | Stop ${stopPctText}`;

      ctx.fillStyle = 'rgba(14, 20, 32, 0.9)';
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.15)';
      ctx.lineWidth = 1;
      
      const textW = ctx.measureText(infoText).width + 16;
      const textH = 18;
      const textX = (leftX + rightX) / 2 - textW / 2;
      const textY = isLong ? p2.y + 4 : p2.y - textH - 4;

      ctx.beginPath();
      ctx.rect(textX, textY, textW, textH);
      ctx.fill();
      ctx.stroke();

      ctx.fillStyle = '#ffffff';
      ctx.font = '10px sans-serif';
      ctx.textBaseline = 'middle';
      ctx.textAlign = 'center';
      ctx.fillText(infoText, (leftX + rightX) / 2, textY + textH / 2);
    }
  } else if (type === 'fibonacci' && screenPts.length >= 2) {
    const p0 = screenPts[0];
    const p1 = screenPts[1];
    if (p0.x !== null && p0.y !== null && p1.x !== null && p1.y !== null) {
      // Draw dotted trendline
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.3)';
      ctx.lineWidth = 1;
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(p0.x, p0.y);
      ctx.lineTo(p1.x, p1.y);
      ctx.stroke();
      ctx.setLineDash([]);

      const left = Math.min(p0.x, p1.x);
      const right = extendRight ? ctx.canvas.width : Math.max(p0.x, p1.x);
      
      const activeLevels = fibLevels || [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0];

      // Draw background shading between active levels
      if (fill) {
        const sorted = [...activeLevels].sort((a, b) => a - b);
        const p0_price = points[0].price;
        const p1_price = points[1] ? points[1].price : (cursorPos ? cursorPos.price : p0_price);
        
        for (let i = 0; i < sorted.length - 1; i++) {
          const r1 = sorted[i];
          const r2 = sorted[i + 1];
          const price1 = p1_price - r1 * (p1_price - p0_price);
          const price2 = p1_price - r2 * (p1_price - p0_price);
          const y1 = mapPointToPixels({ time: points[0].time, price: price1 }).y;
          const y2 = mapPointToPixels({ time: points[0].time, price: price2 }).y;
          if (y1 !== null && y2 !== null) {
            ctx.fillStyle = hexToRgba(color, opacity * 0.08);
            ctx.fillRect(left, Math.min(y1, y2), right - left, Math.abs(y2 - y1));
          }
        }
      }

      activeLevels.forEach((r) => {
        const p0_price = points[0].price;
        const p1_price = points[1] ? points[1].price : (cursorPos ? cursorPos.price : p0_price);
        const levelPrice = p1_price - r * (p1_price - p0_price);
        const levelY = mapPointToPixels({ time: points[0].time, price: levelPrice }).y;
        if (levelY !== null) {
          ctx.strokeStyle = hexToRgba(color, opacity);
          ctx.lineWidth = r === 0.5 ? 1.5 : 1;
          ctx.beginPath();
          ctx.moveTo(left, levelY);
          ctx.lineTo(right, levelY);
          ctx.stroke();

          ctx.fillStyle = 'rgba(255, 255, 255, 0.8)';
          ctx.font = '9px sans-serif';
          ctx.textAlign = 'left';
          ctx.textBaseline = 'bottom';
          ctx.fillText(`${r} (${levelPrice.toFixed(5)})`, left + 5, levelY - 2);
        }
      });
    }
  }
};

export const drawSelectionHandlesOnCanvas = (
  ctx: CanvasRenderingContext2D,
  points: Point[],
  color: string,
  mapPointToPixels: (pt: Point) => { x: number | null; y: number | null }
) => {
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
