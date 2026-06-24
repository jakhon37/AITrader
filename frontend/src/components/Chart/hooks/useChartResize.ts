import { useEffect, useLayoutEffect, useRef } from 'react';
import type { RefObject } from 'react';
import type { IChartApi } from 'lightweight-charts';

function syncChartSize(chart: IChartApi, container: HTMLElement) {
  const { width, height } = container.getBoundingClientRect();
  const w = Math.floor(width);
  const h = Math.floor(height);
  if (w > 0 && h > 0) {
    chart.resize(w, h);
  }
}

/** Force lightweight-charts to match its container after flex layout changes. */
export function useChartResize(
  chart: IChartApi | null,
  containerRef: RefObject<HTMLDivElement | null>,
  options?: {
    layoutKey?: number;
    panelRef?: RefObject<HTMLElement | null>;
    layoutRowRef?: RefObject<HTMLElement | null>;
    panelVisible?: boolean;
    ticketCollapsed?: boolean;
  },
) {
  const {
    layoutKey = 0,
    panelRef,
    layoutRowRef,
    panelVisible = true,
    ticketCollapsed = false,
  } = options ?? {};

  const timersRef = useRef<number[]>([]);

  const clearScheduled = () => {
    timersRef.current.forEach((id) => {
      cancelAnimationFrame(id);
      window.clearTimeout(id);
    });
    timersRef.current = [];
  };

  const scheduleResize = (container: HTMLElement) => {
    if (!chart) return;
    clearScheduled();

    const run = () => syncChartSize(chart, container);
    run();

    timersRef.current.push(
      requestAnimationFrame(() => {
        run();
        timersRef.current.push(requestAnimationFrame(run));
      }),
    );
    timersRef.current.push(window.setTimeout(run, 50));
    timersRef.current.push(window.setTimeout(run, 200));
    timersRef.current.push(window.setTimeout(run, 500));
  };

  // Persistent observers — keep connected across panel toggles.
  useEffect(() => {
    if (!chart || !containerRef.current) return;
    const container = containerRef.current;

    const onResize = () => syncChartSize(chart, container);
    onResize();

    const ro = new ResizeObserver(onResize);
    const observed = new Set<Element>();

    const observe = (el: Element | null | undefined) => {
      if (!el || observed.has(el)) return;
      observed.add(el);
      ro.observe(el);
    };

    observe(container);
    observe(panelRef?.current);
    observe(layoutRowRef?.current);

    const raf = requestAnimationFrame(() => {
      observe(panelRef?.current);
      observe(layoutRowRef?.current);
      onResize();
    });

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, [chart, containerRef, panelRef, layoutRowRef]);

  // Panel show/hide and divider drags settle one or more frames late.
  useLayoutEffect(() => {
    if (!chart || !containerRef.current) return;
    scheduleResize(containerRef.current);
    return clearScheduled;
  }, [chart, containerRef, layoutKey, panelVisible, ticketCollapsed]);

  useEffect(() => () => clearScheduled(), []);
}