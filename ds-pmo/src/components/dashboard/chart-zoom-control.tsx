"use client";

import { memo } from "react";
import { cn } from "@/lib/utils";

interface ChartZoomControlProps {
  zoom: number;
  minZoom: number;
  maxZoom: number;
  onZoomChange: (z: number) => void;
  onReset: () => void;
  className?: string;
}

/**
 * Compact zoom control: a horizontal slider + reset button.
 * Designed to live in ExpandableWidget's `headerRight` slot.
 *
 * UX notes:
 * - Slider is the primary "scroller" — direct, predictable.
 * - Wheel-over-chart and drag-to-pan are handled by useChartZoom.
 * - Reset only shows once the user has actually zoomed.
 */
export const ChartZoomControl = memo(function ChartZoomControl({
  zoom,
  minZoom,
  maxZoom,
  onZoomChange,
  onReset,
  className,
}: ChartZoomControlProps) {
  const isAtDefault = Math.abs(zoom - 1) < 0.001;
  // Slider uses a piecewise-log mapping so the neutral zoom (1×) always sits
  // at a fixed position. When minZoom < 1, that position is the slider
  // midpoint — giving "zoom out" the same range as "zoom in". When minZoom
  // is 1 (no zoom-out), the neutral point collapses to the left edge.
  const NEUTRAL = 1;
  const sliderMax = 100;
  const neutralPos = minZoom < NEUTRAL ? sliderMax / 2 : 0;

  const tToZoom = (t: number): number => {
    if (t <= neutralPos) {
      if (neutralPos === 0) return NEUTRAL;
      const frac = t / neutralPos;
      return minZoom * Math.pow(NEUTRAL / minZoom, frac);
    }
    const frac = (t - neutralPos) / (sliderMax - neutralPos);
    return NEUTRAL * Math.pow(maxZoom / NEUTRAL, frac);
  };
  const zoomToT = (z: number): number => {
    if (z <= NEUTRAL) {
      if (neutralPos === 0) return 0;
      const frac = Math.log(z / minZoom) / Math.log(NEUTRAL / minZoom);
      return Math.max(0, Math.min(neutralPos, frac * neutralPos));
    }
    const frac = Math.log(z / NEUTRAL) / Math.log(maxZoom / NEUTRAL);
    return Math.max(neutralPos, Math.min(sliderMax, neutralPos + frac * (sliderMax - neutralPos)));
  };

  return (
    <div className={cn("flex items-center gap-1.5", className)}>
      <button
        type="button"
        onClick={() => onZoomChange(Math.max(minZoom, zoom / 1.4))}
        disabled={zoom <= minZoom + 0.001}
        className="rounded p-1 text-etex-gray-400 hover:text-etex-gray-700 dark:hover:text-gray-200 hover:bg-etex-gray-100 dark:hover:bg-[#282C34] transition-colors disabled:opacity-30 disabled:hover:bg-transparent disabled:cursor-not-allowed"
        title="Zoom out"
        aria-label="Zoom out"
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="11" cy="11" r="7" />
          <line x1="7.5" y1="11" x2="14.5" y2="11" />
          <line x1="20" y1="20" x2="16" y2="16" />
        </svg>
      </button>

      <input
        type="range"
        min={0}
        max={sliderMax}
        step={1}
        value={zoomToT(zoom)}
        onChange={(e) => onZoomChange(tToZoom(Number(e.target.value)))}
        className="chart-zoom-slider"
        aria-label={`Zoom level ${zoom.toFixed(1)} times`}
        title={`${zoom.toFixed(1)}×`}
      />

      <button
        type="button"
        onClick={() => onZoomChange(Math.min(maxZoom, zoom * 1.4))}
        disabled={zoom >= maxZoom - 0.001}
        className="rounded p-1 text-etex-gray-400 hover:text-etex-gray-700 dark:hover:text-gray-200 hover:bg-etex-gray-100 dark:hover:bg-[#282C34] transition-colors disabled:opacity-30 disabled:hover:bg-transparent disabled:cursor-not-allowed"
        title="Zoom in"
        aria-label="Zoom in"
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="11" cy="11" r="7" />
          <line x1="11" y1="7.5" x2="11" y2="14.5" />
          <line x1="7.5" y1="11" x2="14.5" y2="11" />
          <line x1="20" y1="20" x2="16" y2="16" />
        </svg>
      </button>

      <button
        type="button"
        onClick={onReset}
        className={cn(
          "rounded px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide tabular-nums transition-all",
          !isAtDefault
            ? "text-etex-orange hover:bg-etex-orange/10 cursor-pointer"
            : "text-etex-gray-400 dark:text-gray-500 cursor-default",
        )}
        title={!isAtDefault ? "Reset zoom" : "At default zoom"}
        aria-label={!isAtDefault ? "Reset zoom" : `Zoom level ${zoom.toFixed(1)} times`}
        disabled={isAtDefault}
      >
        {zoom.toFixed(zoom < 1 ? 2 : 1)}×
      </button>
    </div>
  );
});
