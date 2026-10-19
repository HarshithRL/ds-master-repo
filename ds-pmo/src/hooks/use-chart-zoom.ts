"use client";

import { useState, useCallback, useRef, useEffect, useMemo } from "react";

export interface ChartDomain {
  xMin: number;
  xMax: number;
  yMin: number;
  yMax: number;
}

export interface ChartViewport {
  xMin: number;
  xMax: number;
  yMin: number;
  yMax: number;
}

export interface UseChartZoomOptions {
  domain: ChartDomain;
  plot: { left: number; top: number; width: number; height: number };
  /** Max zoom factor (>1 = more zoomed in than default). Default 8. */
  maxZoom?: number;
  /** Min zoom factor (<1 = zoomed out beyond default, exposes more whitespace
   *  around the domain). Default 1 (no zoom-out). */
  minZoom?: number;
}

const DRAG_THRESHOLD_PX = 3;
const WHEEL_STEP = 1.15;

function clampViewportToDomain(vp: ChartViewport, domain: ChartDomain): ChartViewport {
  const dxRange = domain.xMax - domain.xMin;
  const dyRange = domain.yMax - domain.yMin;
  const dxCenter = (domain.xMin + domain.xMax) / 2;
  const dyCenter = (domain.yMin + domain.yMax) / 2;
  let { xMin, xMax, yMin, yMax } = vp;

  const xRange = xMax - xMin;
  if (xRange >= dxRange) {
    // Zoomed out beyond the domain — center on the domain rather than letting
    // the user pan into pure whitespace.
    xMin = dxCenter - xRange / 2;
    xMax = dxCenter + xRange / 2;
  } else {
    if (xMin < domain.xMin) { xMax += domain.xMin - xMin; xMin = domain.xMin; }
    if (xMax > domain.xMax) { xMin -= xMax - domain.xMax; xMax = domain.xMax; }
  }

  const yRange = yMax - yMin;
  if (yRange >= dyRange) {
    yMin = dyCenter - yRange / 2;
    yMax = dyCenter + yRange / 2;
  } else {
    if (yMin < domain.yMin) { yMax += domain.yMin - yMin; yMin = domain.yMin; }
    if (yMax > domain.yMax) { yMin -= yMax - domain.yMax; yMax = domain.yMax; }
  }

  return { xMin, xMax, yMin, yMax };
}

/**
 * Provides zoom + pan state for SVG charts.
 * The viewport is expressed in data units, so dots/labels stay crisp.
 * Zoom is uniform across both axes (single scalar) — keeps the bullseye/quadrants square.
 */
export function useChartZoom({ domain, plot, maxZoom = 8, minZoom = 1 }: UseChartZoomOptions) {
  // Destructure plot to primitives so callbacks/effects depend on stable
  // values, not on the object identity (which consumers may recreate per render).
  const { left: plotLeft, top: plotTop, width: plotWidth, height: plotHeight } = plot;
  const [viewport, setViewport] = useState<ChartViewport>(domain);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const dragRef = useRef<{
    startClientX: number;
    startClientY: number;
    startVp: ChartViewport;
    moved: boolean;
  } | null>(null);

  // Reset viewport whenever the underlying domain bounds change. This is a
  // deliberate cross-prop sync — the lint rule's "cascading renders" concern
  // doesn't apply because in practice domain is a stable module-level constant.
  // eslint-disable-next-line react-hooks/set-state-in-effect, react-hooks/exhaustive-deps
  useEffect(() => { setViewport(domain); }, [domain.xMin, domain.xMax, domain.yMin, domain.yMax]);

  const zoom = useMemo(() => {
    const xz = (domain.xMax - domain.xMin) / (viewport.xMax - viewport.xMin);
    const yz = (domain.yMax - domain.yMin) / (viewport.yMax - viewport.yMin);
    return Math.max(xz, yz);
  }, [domain, viewport]);

  // Drag-to-pan only applies when zoomed *in* — at zoom <= 1 the viewport
  // is centered on the domain and there's nowhere meaningful to pan.
  const isZoomed = zoom > 1.001;
  const isAtDefault = Math.abs(zoom - 1) < 0.001;

  const setZoomLevel = useCallback((newZoom: number) => {
    const z = Math.min(maxZoom, Math.max(minZoom, newZoom));
    setViewport((vp) => {
      const cx = (vp.xMin + vp.xMax) / 2;
      const cy = (vp.yMin + vp.yMax) / 2;
      const newXRange = (domain.xMax - domain.xMin) / z;
      const newYRange = (domain.yMax - domain.yMin) / z;
      return clampViewportToDomain({
        xMin: cx - newXRange / 2,
        xMax: cx + newXRange / 2,
        yMin: cy - newYRange / 2,
        yMax: cy + newYRange / 2,
      }, domain);
    });
  }, [domain, maxZoom, minZoom]);

  const reset = useCallback(() => setViewport(domain), [domain]);

  // Convert a pointer event's client coords into data-space coords.
  // Uses the SVG element's bounding rect plus the viewBox dimensions so it
  // works regardless of CSS scaling.
  const clientToData = useCallback((clientX: number, clientY: number, vp: ChartViewport) => {
    const svg = svgRef.current;
    if (!svg) return { dataX: 0, dataY: 0, insidePlot: false };
    const rect = svg.getBoundingClientRect();
    const vb = svg.viewBox.baseVal;
    const sx = vb.width / rect.width;
    const sy = vb.height / rect.height;
    const userX = (clientX - rect.left) * sx;
    const userY = (clientY - rect.top) * sy;
    const fx = (userX - plotLeft) / plotWidth;
    const fy = (userY - plotTop) / plotHeight;
    const dataX = vp.xMin + fx * (vp.xMax - vp.xMin);
    const dataY = vp.yMax - fy * (vp.yMax - vp.yMin); // svg y flipped
    return {
      dataX,
      dataY,
      insidePlot: fx >= 0 && fx <= 1 && fy >= 0 && fy <= 1,
    };
  }, [plotLeft, plotTop, plotWidth, plotHeight]);

  // Wheel zoom around cursor — attached non-passively so we can preventDefault
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;

    function onWheel(e: WheelEvent) {
      e.preventDefault();
      setViewport((vp) => {
        const { dataX, dataY, insidePlot } = clientToData(e.clientX, e.clientY, vp);
        const focalX = insidePlot ? dataX : (vp.xMin + vp.xMax) / 2;
        const focalY = insidePlot ? dataY : (vp.yMin + vp.yMax) / 2;
        const factor = e.deltaY < 0 ? WHEEL_STEP : 1 / WHEEL_STEP;
        const currentZoom = (domain.xMax - domain.xMin) / (vp.xMax - vp.xMin);
        const newZoom = Math.min(maxZoom, Math.max(minZoom, currentZoom * factor));
        const newXRange = (domain.xMax - domain.xMin) / newZoom;
        const newYRange = (domain.yMax - domain.yMin) / newZoom;
        const fxRatio = (focalX - vp.xMin) / (vp.xMax - vp.xMin);
        const fyRatio = (focalY - vp.yMin) / (vp.yMax - vp.yMin);
        const xMin = focalX - fxRatio * newXRange;
        const yMin = focalY - fyRatio * newYRange;
        return clampViewportToDomain({
          xMin,
          xMax: xMin + newXRange,
          yMin,
          yMax: yMin + newYRange,
        }, domain);
      });
    }

    svg.addEventListener("wheel", onWheel, { passive: false });
    return () => svg.removeEventListener("wheel", onWheel);
  }, [domain, maxZoom, minZoom, clientToData]);

  // Drag-to-pan. Listeners attach on mousedown so they capture window-level
  // motion even if the cursor leaves the SVG.
  const onPointerDown = useCallback((e: React.PointerEvent<SVGSVGElement>) => {
    if (!isZoomed) return;
    if (e.button !== 0) return;
    dragRef.current = {
      startClientX: e.clientX,
      startClientY: e.clientY,
      startVp: viewport,
      moved: false,
    };
  }, [isZoomed, viewport]);

  useEffect(() => {
    function onMove(e: PointerEvent) {
      const drag = dragRef.current;
      if (!drag) return;
      const dxPx = e.clientX - drag.startClientX;
      const dyPx = e.clientY - drag.startClientY;
      if (!drag.moved && Math.hypot(dxPx, dyPx) < DRAG_THRESHOLD_PX) return;
      drag.moved = true;

      const svg = svgRef.current;
      if (!svg) return;
      const rect = svg.getBoundingClientRect();
      const vb = svg.viewBox.baseVal;
      const sx = vb.width / rect.width;
      const sy = vb.height / rect.height;
      const dxUser = dxPx * sx;
      const dyUser = dyPx * sy;
      const xRange = drag.startVp.xMax - drag.startVp.xMin;
      const yRange = drag.startVp.yMax - drag.startVp.yMin;
      const ddx = -(dxUser / plotWidth) * xRange;
      const ddy = (dyUser / plotHeight) * yRange; // svg y flipped → data y inverted
      setViewport(clampViewportToDomain({
        xMin: drag.startVp.xMin + ddx,
        xMax: drag.startVp.xMax + ddx,
        yMin: drag.startVp.yMin + ddy,
        yMax: drag.startVp.yMax + ddy,
      }, domain));
    }
    function onUp() {
      const drag = dragRef.current;
      if (drag?.moved) {
        // Swallow the click that would fire after a drag-pan, so the
        // SVG's onClick (pin-clearing) doesn't fire spuriously.
        const swallow = (ev: MouseEvent) => {
          ev.stopPropagation();
          ev.preventDefault();
          window.removeEventListener("click", swallow, true);
        };
        window.addEventListener("click", swallow, true);
      }
      dragRef.current = null;
    }
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
  }, [domain, plotWidth, plotHeight]);

  return {
    svgRef,
    viewport,
    zoom,
    isZoomed,
    isAtDefault,
    maxZoom,
    minZoom,
    setZoomLevel,
    reset,
    onPointerDown,
  };
}

/**
 * Generate ~`count` "nice" tick values within [min, max].
 * Used to refresh axis labels as the viewport zooms.
 */
export function niceTicks(min: number, max: number, count = 5): number[] {
  const range = max - min;
  if (range <= 0 || !isFinite(range)) return [];
  const rawStep = range / count;
  const mag = Math.pow(10, Math.floor(Math.log10(rawStep)));
  const norm = rawStep / mag;
  let step: number;
  if (norm < 1.5) step = mag;
  else if (norm < 3) step = 2 * mag;
  else if (norm < 7) step = 5 * mag;
  else step = 10 * mag;

  const ticks: number[] = [];
  const start = Math.ceil(min / step - 1e-9) * step;
  for (let v = start; v <= max + step * 1e-6; v += step) {
    const rounded = Math.round(v / step) * step;
    // Avoid -0 and floating-point dust
    ticks.push(Math.abs(rounded) < step * 1e-9 ? 0 : Number(rounded.toFixed(10)));
  }
  return ticks;
}
