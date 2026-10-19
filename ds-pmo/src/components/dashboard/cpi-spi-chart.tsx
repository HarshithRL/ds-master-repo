"use client";

import { useMemo, useState, useCallback, useRef, useEffect, memo } from "react";
import Link from "next/link";
import { cn, formatCurrency } from "@/lib/utils";
import { calcEAC, calcCPI, calcSPI } from "@/lib/calculations";
import { ExpandableWidget } from "./expandable-widget";
import { ChartZoomControl } from "./chart-zoom-control";
import { useChartZoom, niceTicks } from "@/hooks/use-chart-zoom";
import { getPhaseByKey } from "@/lib/constants";
import type { ProjectListItem } from "@/types";

interface CpiSpiChartProps {
  projects: ProjectListItem[];
}

interface ProjectEVM {
  name: string;
  id: string;
  cpi: number;
  spi: number;
  budget: number;
  phaseKey: string;
  phaseColor: string;
  phaseLabel: string;
}

const MIN_INDEX = 0.3;
const MAX_INDEX = 2.0;

function computeEVM(project: ProjectListItem): ProjectEVM | null {
  const cpi = calcCPI(project.budget);
  const spi = calcSPI(project);
  if (cpi == null || spi == null) return null;
  if (cpi < MIN_INDEX || cpi > MAX_INDEX || spi < MIN_INDEX || spi > MAX_INDEX) return null;

  // EAC is guaranteed non-null when calcCPI returned a value.
  const eac = calcEAC(project.budget!);

  const phase = getPhaseByKey(project.currentPhase, project.lifecycleType);
  const phaseColor = phase?.color === "#FFFFFF" ? "#9CA3AF" : (phase?.color ?? "#6B7280");

  return {
    name: project.name,
    id: project.id,
    cpi: Math.round(cpi * 100) / 100,
    spi: Math.round(spi * 100) / 100,
    budget: eac,
    phaseKey: project.currentPhase,
    phaseColor,
    phaseLabel: phase?.shortLabel ?? project.currentPhase,
  };
}

// Chart layout
const CHART_W = 260;
const CHART_H = 210;
const M = { top: 14, right: 14, bottom: 22, left: 26 };
const PW = CHART_W - M.left - M.right;
const PH = CHART_H - M.top - M.bottom;
// Tighter visible domain than the data-validity window (MIN_INDEX/MAX_INDEX).
// Projects valid as data but outside this range render as outward triangles
// on the chart edge instead of being clamped silently.
const D_MIN = 0.7;
const D_MAX = 1.3;
const FULL_DOMAIN = { xMin: D_MIN, xMax: D_MAX, yMin: D_MIN, yMax: D_MAX };

// Quadrant colors encode the asymmetric truth: "ahead-but-over-budget" is
// a worse trade than "behind-but-under-budget", so bottom-right gets a stronger
// warning hue than top-left.
// Rects extend to MIN_INDEX/MAX_INDEX so the fill covers any zoomed-out view
// inside the data-validity window — at zoom 0.5× the visible region (0.4–1.6)
// is still fully covered.
const QUADRANTS = [
  // Top-right: ahead of schedule, under budget (best)
  { x1: 1, y1: 1, x2: MAX_INDEX, y2: MAX_INDEX, fill: "#15803D", label1: "Ahead of schedule", label2: "Below budget" },
  // Top-left: behind schedule, under budget (banked savings)
  { x1: MIN_INDEX, y1: 1, x2: 1, y2: MAX_INDEX, fill: "#86EFAC", label1: "Behind schedule", label2: "Below budget" },
  // Bottom-right: ahead of schedule, over budget (burned money — warning)
  { x1: 1, y1: MIN_INDEX, x2: MAX_INDEX, y2: 1, fill: "#F97316", label1: "Ahead of schedule", label2: "Over budget" },
  // Bottom-left: behind schedule, over budget (worst)
  { x1: MIN_INDEX, y1: MIN_INDEX, x2: 1, y2: 1, fill: "#DC2626", label1: "Behind schedule", label2: "Over budget" },
];

// Text colors that contrast with each quadrant fill
const QUADRANT_TEXT_COLORS = ["#15803D", "#16A34A", "#C2410C", "#DC2626"];

// Bubble sizing
const MIN_R = 3;
const MAX_R = 12;

export const CpiSpiChart = memo(function CpiSpiChart({ projects }: CpiSpiChartProps) {
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);
  const [pinnedIdx, setPinnedIdx] = useState<number | null>(null);
  const [hoveredAvg, setHoveredAvg] = useState<boolean>(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const {
    svgRef,
    viewport,
    zoom,
    isZoomed,
    minZoom,
    maxZoom,
    setZoomLevel,
    reset: resetZoom,
    onPointerDown,
  } = useChartZoom({
    domain: FULL_DOMAIN,
    plot: { left: M.left, top: M.top, width: PW, height: PH },
    minZoom: 0.5,
    maxZoom: 6,
  });

  const sx = useCallback(
    (v: number) => M.left + ((v - viewport.xMin) / (viewport.xMax - viewport.xMin)) * PW,
    [viewport.xMin, viewport.xMax],
  );
  const sy = useCallback(
    (v: number) => M.top + PH - ((v - viewport.yMin) / (viewport.yMax - viewport.yMin)) * PH,
    [viewport.yMin, viewport.yMax],
  );

  const xTicks = useMemo(() => niceTicks(viewport.xMin, viewport.xMax, 6), [viewport.xMin, viewport.xMax]);
  const yTicks = useMemo(() => niceTicks(viewport.yMin, viewport.yMax, 6), [viewport.yMin, viewport.yMax]);
  const fmtTick = useCallback((v: number) => {
    const step = (viewport.xMax - viewport.xMin) / 10;
    const digits = Math.min(4, Math.max(0, -Math.floor(Math.log10(step + 1e-12))));
    return v.toFixed(digits);
  }, [viewport.xMin, viewport.xMax]);

  const activeIdx = pinnedIdx ?? hoveredIdx;

  const data = useMemo(() => {
    return projects.map((p) => computeEVM(p)).filter((d): d is ProjectEVM => d !== null);
  }, [projects]);

  // Budget range for relative sizing
  const budgetRange = useMemo(() => {
    if (data.length === 0) return { min: 0, max: 1 };
    const budgets = data.map((d) => d.budget);
    return { min: Math.min(...budgets), max: Math.max(...budgets) };
  }, [data]);

  function getRadius(budget: number): number {
    if (budgetRange.max === budgetRange.min) return (MIN_R + MAX_R) / 2;
    const t = (budget - budgetRange.min) / (budgetRange.max - budgetRange.min);
    return MIN_R + Math.sqrt(t) * (MAX_R - MIN_R); // sqrt scale for area perception
  }

  const portfolioAvg = useMemo(() => {
    if (data.length === 0) return null;
    let sCpi = 0, sSpi = 0;
    for (const d of data) { sCpi += d.cpi; sSpi += d.spi; }
    return { cpi: sCpi / data.length, spi: sSpi / data.length };
  }, [data]);

  const offChart = useMemo(() => {
    return data.reduce((n, d) =>
      n + (d.cpi < viewport.yMin || d.cpi > viewport.yMax
        || d.spi < viewport.xMin || d.spi > viewport.xMax ? 1 : 0), 0);
  }, [data, viewport]);

  const excluded = useMemo(() => {
    let total = 0;
    for (const p of projects) {
      const cpi = calcCPI(p.budget);
      const spi = calcSPI(p);
      if (cpi == null || spi == null) continue;
      if (cpi < MIN_INDEX || cpi > MAX_INDEX || spi < MIN_INDEX || spi > MAX_INDEX) total++;
    }
    return total;
  }, [projects]);

  useEffect(() => {
    if (pinnedIdx === null) return;
    function handleClick(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setPinnedIdx(null);
      }
    }
    document.addEventListener("click", handleClick);
    return () => document.removeEventListener("click", handleClick);
  }, [pinnedIdx]);

  const handleDotClick = useCallback((idx: number, e: React.MouseEvent) => {
    e.stopPropagation();
    setPinnedIdx((prev) => (prev === idx ? null : idx));
  }, []);

  if (data.length === 0) {
    return (
      <ExpandableWidget title="CPI vs SPI">
        <div className="p-4 text-xs text-etex-gray-400 text-center py-8">
          Insufficient data for EVM analysis
        </div>
      </ExpandableWidget>
    );
  }

  const clampX = (v: number) => Math.max(viewport.xMin, Math.min(viewport.xMax, v));
  const clampY = (v: number) => Math.max(viewport.yMin, Math.min(viewport.yMax, v));
  const activeData = activeIdx !== null ? data[activeIdx] : null;

  const zoomControl = (
    <ChartZoomControl
      zoom={zoom}
      minZoom={minZoom}
      maxZoom={maxZoom}
      onZoomChange={setZoomLevel}
      onReset={resetZoom}
    />
  );

  // Hide decorative labels at high zoom where they'd be cropped or off-context.
  const showDecoration = !isZoomed;

  return (
    <ExpandableWidget title="CPI vs SPI" headerRight={zoomControl}>
      <div className="p-3" ref={containerRef}>
        <svg
          ref={svgRef}
          viewBox={`0 0 ${CHART_W} ${CHART_H}`}
          className={cn("w-full select-none touch-none", isZoomed && "cursor-grab active:cursor-grabbing")}
          onClick={() => setPinnedIdx(null)}
          onPointerDown={onPointerDown}
        >
          <defs>
            <clipPath id="cpi-spi-clip">
              <rect x={M.left} y={M.top} width={PW} height={PH} />
            </clipPath>
            {/* Quadrant overlays — slightly stronger so colors actually read */}
            {QUADRANTS.map((q, i) => (
              <linearGradient key={i} id={`q-grad-${i}`} x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor={q.fill} stopOpacity={0.18} />
                <stop offset="100%" stopColor={q.fill} stopOpacity={0.06} />
              </linearGradient>
            ))}
          </defs>

          {/* Quadrant backgrounds */}
          <g clipPath="url(#cpi-spi-clip)">
            {QUADRANTS.map((q, i) => {
              const rx = sx(q.x1);
              const ry = sy(q.y2);
              const rw = sx(q.x2) - sx(q.x1);
              const rh = sy(q.y1) - sy(q.y2);
              // Anchor labels to the visible corner — intersection of the
              // quadrant rect with the current viewport — so they stay readable
              // at any zoom level instead of drifting off the plot.
              const visX1 = Math.max(q.x1, viewport.xMin);
              const visX2 = Math.min(q.x2, viewport.xMax);
              const visY1 = Math.max(q.y1, viewport.yMin);
              const visY2 = Math.min(q.y2, viewport.yMax);
              const hasVisible = visX1 < visX2 && visY1 < visY2;
              const labelX = i % 2 === 0
                ? sx(visX2) - 4  // right-aligned for right quadrants
                : sx(visX1) + 4; // left-aligned for left quadrants
              const labelY = i < 2
                ? sy(visY2) + 8  // top-aligned for top quadrants
                : sy(visY1) - 6; // bottom-aligned for bottom quadrants
              const anchor = i % 2 === 0 ? "end" : "start";

              return (
                <g key={i}>
                  <rect x={rx} y={ry} width={rw} height={rh} fill={`url(#q-grad-${i})`} />
                  <rect x={rx} y={ry} width={rw} height={rh} fill="none" stroke={q.fill} strokeWidth={0} />
                  {showDecoration && hasVisible && (
                    <>
                      <text
                        x={labelX}
                        y={labelY}
                        textAnchor={anchor}
                        fontSize={3.8}
                        fill={QUADRANT_TEXT_COLORS[i]}
                        opacity={0.55}
                        fontWeight={700}
                        letterSpacing="0.02em"
                        style={{ textTransform: "uppercase" } as React.CSSProperties}
                      >
                        {q.label1}
                      </text>
                      <text
                        x={labelX}
                        y={labelY + 5}
                        textAnchor={anchor}
                        fontSize={3.8}
                        fill={QUADRANT_TEXT_COLORS[i]}
                        opacity={0.55}
                        fontWeight={700}
                        letterSpacing="0.02em"
                        style={{ textTransform: "uppercase" } as React.CSSProperties}
                      >
                        {q.label2}
                      </text>
                    </>
                  )}
                </g>
              );
            })}
          </g>

          {/* Grid lines */}
          <g clipPath="url(#cpi-spi-clip)">
            {xTicks.map((t) => (
              <line
                key={`vx-${t}`}
                x1={sx(t)} y1={M.top} x2={sx(t)} y2={M.top + PH}
                stroke={Math.abs(t - 1) < 1e-9 ? "#94A3B8" : "#E2E8F0"}
                strokeWidth={Math.abs(t - 1) < 1e-9 ? 0.8 : 0.3}
                strokeDasharray={Math.abs(t - 1) < 1e-9 ? "3 2" : undefined}
                opacity={Math.abs(t - 1) < 1e-9 ? 0.9 : 0.5}
              />
            ))}
            {yTicks.map((t) => (
              <line
                key={`vy-${t}`}
                x1={M.left} y1={sy(t)} x2={M.left + PW} y2={sy(t)}
                stroke={Math.abs(t - 1) < 1e-9 ? "#94A3B8" : "#E2E8F0"}
                strokeWidth={Math.abs(t - 1) < 1e-9 ? 0.8 : 0.3}
                strokeDasharray={Math.abs(t - 1) < 1e-9 ? "3 2" : undefined}
                opacity={Math.abs(t - 1) < 1e-9 ? 0.9 : 0.5}
              />
            ))}
          </g>

          {/* Axis tick labels */}
          {xTicks.map((t) => (
            <text
              key={`lx-${t}`}
              x={sx(t)} y={M.top + PH + 9}
              textAnchor="middle" fontSize={5}
              fill={Math.abs(t - 1) < 1e-9 ? "#475569" : "#94A3B8"}
              fontWeight={Math.abs(t - 1) < 1e-9 ? 700 : 400}
              fontFamily="system-ui, -apple-system, sans-serif"
            >
              {fmtTick(t)}
            </text>
          ))}
          {yTicks.map((t) => (
            <text
              key={`ly-${t}`}
              x={M.left - 3} y={sy(t) + 1.5}
              textAnchor="end" fontSize={5}
              fill={Math.abs(t - 1) < 1e-9 ? "#475569" : "#94A3B8"}
              fontWeight={Math.abs(t - 1) < 1e-9 ? 700 : 400}
              fontFamily="system-ui, -apple-system, sans-serif"
            >
              {fmtTick(t)}
            </text>
          ))}

          {/* Axis labels */}
          <text
            x={M.left + PW / 2} y={CHART_H - 2}
            textAnchor="middle" fontSize={5.5}
            fill="#64748B" fontWeight={600}
            fontFamily="system-ui, -apple-system, sans-serif"
            letterSpacing="0.04em"
          >
            SPI (Schedule Performance)
          </text>
          <text
            x={6} y={M.top + PH / 2}
            textAnchor="middle" fontSize={5.5}
            fill="#64748B" fontWeight={600}
            fontFamily="system-ui, -apple-system, sans-serif"
            letterSpacing="0.04em"
            transform={`rotate(-90, 6, ${M.top + PH / 2})`}
          >
            CPI (Cost Performance)
          </text>

          {/* TARGET cue — placed inside the plot next to the (1,1) crosshair
              so it can't collide with the SPI axis title underneath. Hidden
              when zoom would push it off the plot or noise becomes overkill. */}
          {showDecoration && 1 >= viewport.xMin && 1 <= viewport.xMax && 1 >= viewport.yMin && 1 <= viewport.yMax && (
            <text x={sx(1) + 2.5} y={sy(1) - 2.5} fontSize={3.5} fill="#64748B" fontWeight={700}
                  fontFamily="Arial, sans-serif" letterSpacing="0.05em"
                  style={{ textTransform: "uppercase" } as React.CSSProperties}>
              target
            </text>
          )}

          {/* Data points — circles for in-range, triangles for off-chart outliers */}
          <g clipPath="url(#cpi-spi-clip)">
            {data
              .map((d, i) => ({ d, i, r: getRadius(d.budget) }))
              .sort((a, b) => b.r - a.r)
              .map(({ d, i, r }) => {
                const cHigh = d.cpi > viewport.yMax, cLow = d.cpi < viewport.yMin;
                const sHigh = d.spi > viewport.xMax, sLow = d.spi < viewport.xMin;
                const isOut = cHigh || cLow || sHigh || sLow;
                const cx = sx(clampX(d.spi));
                const cy = sy(clampY(d.cpi));
                const isActive = activeIdx === i;
                const commonProps = {
                  className: "cursor-pointer transition-all duration-150",
                  onMouseEnter: () => { if (pinnedIdx === null) setHoveredIdx(i); },
                  onMouseLeave: () => { if (pinnedIdx === null) setHoveredIdx(null); },
                  onClick: (e: React.MouseEvent) => handleDotClick(i, e),
                };

                if (isOut) {
                  // Outward unit vector — SVG y is flipped.
                  const ux = (sHigh ? 1 : 0) + (sLow ? -1 : 0);
                  const uyRaw = (cHigh ? -1 : 0) + (cLow ? 1 : 0);
                  const mag = Math.hypot(ux, uyRaw) || 1;
                  const ndx = ux / mag, ndy = uyRaw / mag;
                  // Tip kisses the chart edge, base sits inward — triangle is
                  // fully inside the plot, no clipping.
                  const size = Math.max(r * 1.6, 7);
                  const tipX = cx;
                  const tipY = cy;
                  const baseX = cx - ndx * size;
                  const baseY = cy - ndy * size;
                  const px = -ndy, py = ndx;
                  const halfW = size * 0.65;
                  const b1x = baseX + px * halfW;
                  const b1y = baseY + py * halfW;
                  const b2x = baseX - px * halfW;
                  const b2y = baseY - py * halfW;
                  return (
                    <g key={i} {...commonProps}>
                      <polygon
                        points={`${tipX},${tipY} ${b1x},${b1y} ${b2x},${b2y}`}
                        fill={d.phaseColor} fillOpacity={isActive ? 1 : 0.92}
                        stroke="rgba(0,0,0,0.35)" strokeWidth={0.7}
                        strokeLinejoin="round"
                        style={{
                          transformOrigin: `${cx}px ${cy}px`,
                          transform: isActive ? "scale(1.25)" : "scale(1)",
                          transition: "transform 180ms cubic-bezier(.4,0,.2,1), fill-opacity 180ms ease",
                        }}
                      />
                      <circle cx={baseX} cy={baseY} r={size * 0.9} fill="transparent" />
                    </g>
                  );
                }

                return (
                  <g key={i} {...commonProps}>
                    <circle
                      cx={cx} cy={cy} r={r}
                      fill={d.phaseColor} fillOpacity={isActive ? 1 : 0.85}
                      stroke="rgba(0,0,0,0.18)" strokeWidth={0.6}
                      style={{
                        transformOrigin: `${cx}px ${cy}px`,
                        transform: isActive ? "scale(1.35)" : "scale(1)",
                        transition: "transform 180ms cubic-bezier(.4,0,.2,1), fill-opacity 180ms ease",
                      }}
                    />
                    <circle cx={cx} cy={cy} r={Math.max(r + 2, 8)} fill="transparent" />
                  </g>
                );
              })}
          </g>

          {/* Portfolio average — small crosshair, hoverable */}
          {portfolioAvg && (() => {
            const pcx = sx(clampX(portfolioAvg.spi));
            const pcy = sy(clampY(portfolioAvg.cpi));
            return (
              <g
                clipPath="url(#cpi-spi-clip)"
                className="cursor-pointer"
                onMouseEnter={() => { if (pinnedIdx === null) setHoveredAvg(true); }}
                onMouseLeave={() => setHoveredAvg(false)}
              >
                <circle cx={pcx} cy={pcy} r={5.5} fill="white" fillOpacity={0.92}
                        stroke="#0F172A" strokeWidth={1.1} />
                <line x1={pcx - 3.4} y1={pcy} x2={pcx + 3.4} y2={pcy}
                      stroke="#0F172A" strokeWidth={1} />
                <line x1={pcx} y1={pcy - 3.4} x2={pcx} y2={pcy + 3.4}
                      stroke="#0F172A" strokeWidth={1} />
                <text x={pcx + 7.5} y={pcy + 1.6} fontSize={4.2} fontWeight={700}
                      fill="#0F172A" fontFamily="Arial, sans-serif">
                  AVG
                </text>
                <circle cx={pcx} cy={pcy} r={9} fill="transparent" />
              </g>
            );
          })()}
        </svg>

        {/* Detail strip: portfolio average takes priority when hovered with no active project */}
        {hoveredAvg && !activeData && portfolioAvg ? (
          <div className="mt-2 flex flex-wrap items-center justify-between gap-2 rounded-lg px-3 py-2.5 text-[11px] border bg-white/80 dark:bg-gray-900/60 backdrop-blur-sm shadow-sm"
               style={{ borderColor: "#0F172A40", boxShadow: "0 0 0 1px #0F172A15, 0 2px 8px #0F172A10" }}>
            <div className="flex items-center gap-2 min-w-0">
              <span className="w-3 h-3 rounded-full shrink-0 ring-2 ring-white dark:ring-gray-900 bg-slate-900" />
              <div className="min-w-0">
                <span className="font-semibold text-etex-gray-800 dark:text-gray-200 truncate block leading-tight">
                  Portfolio Average
                </span>
                <span className="text-[9px] font-medium text-etex-gray-500">
                  {data.length} project{data.length !== 1 ? "s" : ""}
                </span>
              </div>
            </div>
            <div className="flex items-center gap-3 shrink-0 flex-wrap">
              <div className="text-center">
                <span className="block text-[8px] uppercase tracking-wider text-etex-gray-400 font-semibold">CPI</span>
                <span className="font-bold text-etex-gray-800 dark:text-gray-200">{portfolioAvg.cpi.toFixed(2)}</span>
              </div>
              <div className="text-center">
                <span className="block text-[8px] uppercase tracking-wider text-etex-gray-400 font-semibold">SPI</span>
                <span className="font-bold text-etex-gray-800 dark:text-gray-200">{portfolioAvg.spi.toFixed(2)}</span>
              </div>
            </div>
          </div>
        ) : activeData ? (
          <div
            className={cn(
              "mt-2 flex flex-wrap items-center justify-between gap-2 rounded-lg px-3 py-2.5 text-[11px] transition-all border",
              "bg-white/80 dark:bg-gray-900/60 backdrop-blur-sm shadow-sm",
            )}
            style={{
              borderColor: `${activeData.phaseColor}40`,
              boxShadow: `0 0 0 1px ${activeData.phaseColor}15, 0 2px 8px ${activeData.phaseColor}10`,
            }}
          >
            <div className="flex items-center gap-2 min-w-0">
              <span
                className="w-3 h-3 rounded-full shrink-0 ring-2 ring-white dark:ring-gray-900"
                style={{ backgroundColor: activeData.phaseColor }}
              />
              <div className="min-w-0">
                <span className="font-semibold text-etex-gray-800 dark:text-gray-200 truncate block leading-tight">
                  {activeData.name}
                </span>
                <span className="text-[9px] font-medium" style={{ color: activeData.phaseColor }}>
                  {activeData.phaseLabel}
                </span>
              </div>
            </div>
            <div className="flex items-center gap-3 shrink-0 flex-wrap">
              <div className="text-center">
                <span className="block text-[8px] uppercase tracking-wider text-etex-gray-400 font-semibold">CPI</span>
                <span className="font-bold text-etex-gray-800 dark:text-gray-200">{activeData.cpi.toFixed(2)}</span>
              </div>
              <div className="text-center">
                <span className="block text-[8px] uppercase tracking-wider text-etex-gray-400 font-semibold">SPI</span>
                <span className="font-bold text-etex-gray-800 dark:text-gray-200">{activeData.spi.toFixed(2)}</span>
              </div>
              <div className="text-center">
                <span className="block text-[8px] uppercase tracking-wider text-etex-gray-400 font-semibold">Budget</span>
                <span className="font-bold text-etex-gray-800 dark:text-gray-200">{formatCurrency(activeData.budget, { compact: true })}</span>
              </div>
              <Link
                href={`/projects/${activeData.id}`}
                className="ml-1 rounded-md bg-etex-charcoal px-2.5 py-1.5 text-[10px] font-semibold text-white hover:bg-etex-gray-700 transition-colors dark:bg-gray-700 dark:hover:bg-gray-600"
                onClick={(e) => e.stopPropagation()}
              >
                View
              </Link>
            </div>
          </div>
        ) : (
          <div className="mt-2 flex items-center gap-2 rounded-lg border border-dashed border-etex-gray-200 dark:border-gray-700 px-3 py-2.5 text-[11px] text-etex-gray-400 dark:text-gray-500">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="shrink-0 opacity-50">
              <circle cx="11" cy="11" r="8" />
              <path d="m21 21-4.3-4.3" />
            </svg>
            Hover or click a bubble to see details — size reflects budget
          </div>
        )}

        {(offChart > 0 || excluded > 0) && (
          <p className="text-[10px] text-etex-gray-400 mt-2">
            {offChart > 0 && (
              <span>
                {offChart} off-chart (triangles, outside {fmtTick(viewport.xMin)}–{fmtTick(viewport.xMax)})
              </span>
            )}
            {offChart > 0 && excluded > 0 && <span> · </span>}
            {excluded > 0 && (
              <span>
                {excluded} outlier{excluded !== 1 ? "s" : ""} excluded (outside {MIN_INDEX}–{MAX_INDEX})
              </span>
            )}
          </p>
        )}
      </div>
    </ExpandableWidget>
  );
});
