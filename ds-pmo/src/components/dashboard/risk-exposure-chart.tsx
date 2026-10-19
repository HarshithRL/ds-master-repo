"use client";

import { useMemo, useState, useCallback, useRef, useEffect, memo } from "react";
import Link from "next/link";
import { cn, formatCurrency } from "@/lib/utils";
import { calcEAC, calcPlannedDuration, getProjectStartDate } from "@/lib/calculations";
import { ExpandableWidget } from "./expandable-widget";
import { ChartZoomControl } from "./chart-zoom-control";
import { useChartZoom, niceTicks } from "@/hooks/use-chart-zoom";
import { getPhaseByKey } from "@/lib/constants";
import type { ProjectListItem } from "@/types";

interface RiskExposureChartProps {
  projects: ProjectListItem[];
}

interface ProjectRiskExposure {
  name: string;
  id: string;
  costPct: number;
  timePct: number;
  costKeur: number;
  timeDays: number;
  eac: number;
  phaseKey: string;
  phaseColor: string;
  phaseLabel: string;
  clampedCost: boolean;
  clampedTime: boolean;
  severity: number;
  bandIdx: number;
}

// Domain: 0–50% on both axes. Anything beyond is clamped to the edge.
const D_MIN = 0;
const D_MAX = 50;

// Severity uses an L^p norm with p<1 so a project with risk on BOTH axes scores
// worse than one with the same number concentrated on a single axis. p=0.85
// keeps the inward-curving "splined" shape but with a gentler compound penalty.
const P_NORM = 0.85;
const P_EXP = 2 / P_NORM; // parametric exponent for the contour curve

// Outer Critical ring extends past the chart's diagonal corner so the whole
// top-right region reads as Critical instead of empty white.
// severity(50, 50) under p=0.85 ≈ 117, so r2=150 covers everything.
const OUTER_R = 150;

// Forgiving thresholds — Contained reaches 20% single-axis. Critical kicks in
// at 50% single-axis or strongly compound exposure.
const BANDS = [
  { r1: 0,  r2: 20,      fill: "#4ADE80", label: "Contained", text: "#15803D", surface: 0.32 },
  { r1: 20, r2: 35,      fill: "#FBBF24", label: "Watch",     text: "#A16207", surface: 0.36 },
  { r1: 35, r2: 50,      fill: "#FB923C", label: "Concern",   text: "#C2410C", surface: 0.38 },
  { r1: 50, r2: OUTER_R, fill: "#F87171", label: "Critical",  text: "#DC2626", surface: 0.42 },
];

function severityScore(costPct: number, timePct: number): number {
  const c = Math.max(0, costPct);
  const t = Math.max(0, timePct);
  if (c === 0 && t === 0) return 0;
  // L^p norm with p<1 — penalizes risk on BOTH axes simultaneously.
  return Math.pow(Math.pow(c, P_NORM) + Math.pow(t, P_NORM), 1 / P_NORM);
}

function bandIndex(severity: number): number {
  for (let i = 0; i < BANDS.length; i++) {
    if (severity < BANDS[i].r2) return i;
  }
  return BANDS.length - 1;
}

function computeExposure(project: ProjectListItem): ProjectRiskExposure | null {
  const budget = project.budget;
  if (!budget || budget.bac <= 0) return null;
  const eac = calcEAC(budget);
  if (eac <= 0) return null;

  if (!project.plannedCompletionDate) return null;
  const start = getProjectStartDate(project);
  const plannedDays = calcPlannedDuration(start, project.plannedCompletionDate);
  if (plannedDays <= 0) return null;

  const costKeur = project.riskSummary.totalCostAtRisk;
  const timeDays = project.riskSummary.totalTimeImpact;

  // Skip projects with literally no exposure recorded — they'd just stack at origin.
  if (costKeur <= 0 && timeDays <= 0) return null;

  const costPctRaw = (costKeur / eac) * 100;
  const timePctRaw = (timeDays / plannedDays) * 100;

  const costPct = Math.max(D_MIN, Math.min(D_MAX, costPctRaw));
  const timePct = Math.max(D_MIN, Math.min(D_MAX, timePctRaw));

  const phase = getPhaseByKey(project.currentPhase, project.lifecycleType);
  const phaseColor = phase?.color === "#FFFFFF" ? "#9CA3AF" : (phase?.color ?? "#6B7280");

  const sev = severityScore(costPct, timePct);

  return {
    name: project.name,
    id: project.id,
    costPct: Math.round(costPct * 10) / 10,
    timePct: Math.round(timePct * 10) / 10,
    costKeur,
    timeDays,
    eac,
    phaseKey: project.currentPhase,
    phaseColor,
    phaseLabel: phase?.shortLabel ?? project.currentPhase,
    clampedCost: costPctRaw > D_MAX,
    clampedTime: timePctRaw > D_MAX,
    severity: Math.round(sev * 10) / 10,
    bandIdx: bandIndex(sev),
  };
}

// viewBox aspect matches the CPI/SPI chart (260x210) so the two widgets render
// at the same height when both are width-stretched. Plot area is kept square
// (centered horizontally) so the bullseye rings stay perfectly circular.
const CHART_W = 260;
const CHART_H = 210;
const M = { top: 10, right: 40, bottom: 20, left: 40 };
const PW = CHART_W - M.left - M.right; // 180
const PH = CHART_H - M.top - M.bottom; // 180

const FULL_DOMAIN = { xMin: D_MIN, xMax: D_MAX, yMin: D_MIN, yMax: D_MAX };

// Quarter-band path in the first quadrant of the bullseye, bounded by two
// p-norm contours (inner severity r1, outer severity r2). The boundaries are
// parametrized as x(θ) = r·cos(θ)^(2/p), y(θ) = r·sin(θ)^(2/p) for θ∈[0, π/2],
// which traces the curve c^p + t^p = r^p. A polyline with N segments
// approximates the contour smoothly enough to look splined at any zoom.
const CONTOUR_SEGMENTS = 80;

function contourPoint(theta: number, r: number, scale: number): { dx: number; dy: number } {
  const cosT = Math.cos(theta);
  const sinT = Math.sin(theta);
  return {
    dx: r * Math.pow(cosT, P_EXP) * scale,
    dy: r * Math.pow(sinT, P_EXP) * scale,
  };
}

function bandPath(ox: number, oy: number, r1: number, r2: number, scale: number): string {
  const parts: string[] = [];
  for (let i = 0; i <= CONTOUR_SEGMENTS; i++) {
    const theta = (i / CONTOUR_SEGMENTS) * (Math.PI / 2);
    const { dx, dy } = contourPoint(theta, r2, scale);
    parts.push(`${i === 0 ? "M" : "L"}${(ox + dx).toFixed(2)},${(oy - dy).toFixed(2)}`);
  }
  if (r1 <= 0) {
    parts.push(`L${ox.toFixed(2)},${oy.toFixed(2)}`);
    parts.push("Z");
    return parts.join(" ");
  }
  for (let i = CONTOUR_SEGMENTS; i >= 0; i--) {
    const theta = (i / CONTOUR_SEGMENTS) * (Math.PI / 2);
    const { dx, dy } = contourPoint(theta, r1, scale);
    parts.push(`L${(ox + dx).toFixed(2)},${(oy - dy).toFixed(2)}`);
  }
  parts.push("Z");
  return parts.join(" ");
}

const MIN_R = 3;
const MAX_R = 12;

export const RiskExposureChart = memo(function RiskExposureChart({ projects }: RiskExposureChartProps) {
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
  const scale = useMemo(() => PW / (viewport.xMax - viewport.xMin), [viewport.xMin, viewport.xMax]);

  const xTicks = useMemo(() => niceTicks(viewport.xMin, viewport.xMax, 5), [viewport.xMin, viewport.xMax]);
  const yTicks = useMemo(() => niceTicks(viewport.yMin, viewport.yMax, 5), [viewport.yMin, viewport.yMax]);
  const fmtTick = useCallback((v: number) => {
    const step = (viewport.xMax - viewport.xMin) / 10;
    const digits = Math.min(2, Math.max(0, -Math.floor(Math.log10(step + 1e-12)) + 1));
    return digits === 0 ? Math.round(v).toString() : v.toFixed(digits);
  }, [viewport.xMin, viewport.xMax]);

  const activeIdx = pinnedIdx ?? hoveredIdx;

  const data = useMemo(() => {
    return projects.map((p) => computeExposure(p)).filter((d): d is ProjectRiskExposure => d !== null);
  }, [projects]);

  const eacRange = useMemo(() => {
    if (data.length === 0) return { min: 0, max: 1 };
    const eacs = data.map((d) => d.eac);
    return { min: Math.min(...eacs), max: Math.max(...eacs) };
  }, [data]);

  function getRadius(eac: number): number {
    if (eacRange.max === eacRange.min) return (MIN_R + MAX_R) / 2;
    const t = (eac - eacRange.min) / (eacRange.max - eacRange.min);
    return MIN_R + Math.sqrt(t) * (MAX_R - MIN_R);
  }

  const bandCounts = useMemo(() => {
    const counts = BANDS.map(() => 0);
    for (const d of data) counts[d.bandIdx]++;
    return counts;
  }, [data]);

  const portfolioAvg = useMemo(() => {
    if (data.length === 0) return null;
    let sCost = 0, sTime = 0;
    for (const d of data) { sCost += d.costPct; sTime += d.timePct; }
    const cost = sCost / data.length;
    const time = sTime / data.length;
    return {
      cost: Math.round(cost * 10) / 10,
      time: Math.round(time * 10) / 10,
      sev: Math.round(severityScore(cost, time) * 10) / 10,
      band: bandIndex(severityScore(cost, time)),
    };
  }, [data]);

  // Count projects with no recorded exposure — surfaced as a footnote so
  // viewers know the chart is not the full portfolio.
  const noExposure = useMemo(() => {
    let n = 0;
    for (const p of projects) {
      if (!p.budget || p.budget.bac <= 0) continue;
      if (!p.plannedCompletionDate) continue;
      const eac = calcEAC(p.budget);
      if (eac <= 0) continue;
      const days = calcPlannedDuration(getProjectStartDate(p), p.plannedCompletionDate);
      if (days <= 0) continue;
      if (p.riskSummary.totalCostAtRisk <= 0 && p.riskSummary.totalTimeImpact <= 0) n++;
    }
    return n;
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
      <ExpandableWidget title="Risk Bullseye">
        <div className="p-4 text-xs text-etex-gray-400 text-center py-8">
          No projects with recorded cost or time at risk
        </div>
      </ExpandableWidget>
    );
  }

  const activeData = activeIdx !== null ? data[activeIdx] : null;
  const ORIGIN_X = sx(0);
  const ORIGIN_Y = sy(0);

  const zoomControl = (
    <ChartZoomControl
      zoom={zoom}
      minZoom={minZoom}
      maxZoom={maxZoom}
      onZoomChange={setZoomLevel}
      onReset={resetZoom}
    />
  );

  return (
    <ExpandableWidget title="Risk Bullseye" headerRight={zoomControl}>
      <div className="p-3" ref={containerRef}>
        <svg
          ref={svgRef}
          viewBox={`0 0 ${CHART_W} ${CHART_H}`}
          className={cn("w-full select-none touch-none", isZoomed && "cursor-grab active:cursor-grabbing")}
          onClick={() => setPinnedIdx(null)}
          onPointerDown={onPointerDown}
        >
          <defs>
            <clipPath id="risk-bullseye-clip">
              <rect x={M.left} y={M.top} width={PW} height={PH} />
            </clipPath>
          </defs>

          {/* Concentric severity bands — p-norm contours fill the whole plot */}
          <g clipPath="url(#risk-bullseye-clip)">
            {BANDS.map((b, i) => (
              <path
                key={i}
                d={bandPath(ORIGIN_X, ORIGIN_Y, b.r1, b.r2, scale)}
                fill={b.fill}
                fillOpacity={b.surface}
              />
            ))}
            {/* Crisp white separators between bands so adjacent colors don't blur */}
            {BANDS.slice(0, -1).map((b, i) => (
              <path
                key={`sep-${i}`}
                d={bandPath(ORIGIN_X, ORIGIN_Y, b.r2 - 0.12, b.r2 + 0.12, scale)}
                fill="#FFFFFF"
                fillOpacity={0.7}
              />
            ))}
          </g>

          {/* Faint orthogonal grid — keeps the raw % readable behind the rings */}
          <g clipPath="url(#risk-bullseye-clip)">
            {xTicks.map((t) => (
              <line
                key={`vx-${t}`}
                x1={sx(t)} y1={M.top} x2={sx(t)} y2={M.top + PH}
                stroke="#E2E8F0" strokeWidth={0.3} opacity={0.4}
              />
            ))}
            {yTicks.map((t) => (
              <line
                key={`vy-${t}`}
                x1={M.left} y1={sy(t)} x2={M.left + PW} y2={sy(t)}
                stroke="#E2E8F0" strokeWidth={0.3} opacity={0.4}
              />
            ))}
          </g>

          {/* Axis tick labels */}
          {xTicks.map((t) => (
            <text
              key={`lx-${t}`}
              x={sx(t)} y={M.top + PH + 9}
              textAnchor="middle" fontSize={5}
              fill="#94A3B8"
              fontFamily="system-ui, -apple-system, sans-serif"
            >
              {fmtTick(t)}%
            </text>
          ))}
          {yTicks.map((t) => (
            <text
              key={`ly-${t}`}
              x={M.left - 3} y={sy(t) + 1.5}
              textAnchor="end" fontSize={5}
              fill="#94A3B8"
              fontFamily="system-ui, -apple-system, sans-serif"
            >
              {fmtTick(t)}%
            </text>
          ))}

          {/* Axis titles */}
          <text
            x={M.left + PW / 2} y={CHART_H - 2}
            textAnchor="middle" fontSize={5.5}
            fill="#64748B" fontWeight={600}
            fontFamily="system-ui, -apple-system, sans-serif"
            letterSpacing="0.04em"
          >
            Time at Risk (% of planned duration)
          </text>
          <text
            x={6} y={M.top + PH / 2}
            textAnchor="middle" fontSize={5.5}
            fill="#64748B" fontWeight={600}
            fontFamily="system-ui, -apple-system, sans-serif"
            letterSpacing="0.04em"
            transform={`rotate(-90, 6, ${M.top + PH / 2})`}
          >
            Cost at Risk (% of EAC)
          </text>


          {/* Project dots — phase color, sized by EAC */}
          <g clipPath="url(#risk-bullseye-clip)">
            {data
              .map((d, i) => ({ d, i, r: getRadius(d.eac) }))
              .sort((a, b) => b.r - a.r)
              .map(({ d, i, r }) => {
                const cx = sx(d.timePct);
                const cy = sy(d.costPct);
                const isActive = activeIdx === i;
                return (
                  <g
                    key={i}
                    className="cursor-pointer transition-all duration-150"
                    onMouseEnter={() => { if (pinnedIdx === null) setHoveredIdx(i); }}
                    onMouseLeave={() => { if (pinnedIdx === null) setHoveredIdx(null); }}
                    onClick={(e) => handleDotClick(i, e)}
                  >
                    <circle
                      cx={cx} cy={cy} r={r}
                      fill={d.phaseColor} fillOpacity={isActive ? 1 : 0.9}
                      stroke="rgba(0,0,0,0.25)" strokeWidth={0.6}
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
            const pcx = sx(Math.max(D_MIN, Math.min(D_MAX, portfolioAvg.time)));
            const pcy = sy(Math.max(D_MIN, Math.min(D_MAX, portfolioAvg.cost)));
            return (
              <g
                clipPath="url(#risk-bullseye-clip)"
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

        {/* Severity band legend — horizontal strip under the chart */}
        <div className="mt-1.5 flex items-center justify-center gap-1.5 flex-wrap">
          {BANDS.map((b, i) => (
            <span
              key={b.label}
              className="flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold"
              style={{ backgroundColor: `${b.fill}1F`, color: b.text, fontFamily: "Arial, sans-serif" }}
            >
              <span
                className="inline-block w-2 h-2 rounded-sm ring-1 ring-black/10"
                style={{ backgroundColor: b.fill }}
              />
              {b.label}
              <span className="opacity-70 font-normal">{bandCounts[i]}</span>
              <span className="opacity-50 text-[8.5px] font-normal">≥{b.r1}%</span>
            </span>
          ))}
        </div>

        {hoveredAvg && !activeData && portfolioAvg ? (
          <div className="mt-2 flex flex-wrap items-center justify-between gap-2 rounded-lg px-3 py-2.5 text-[11px] border bg-white/80 dark:bg-gray-900/60 backdrop-blur-sm shadow-sm"
               style={{ borderColor: "#0F172A40", boxShadow: "0 0 0 1px #0F172A15, 0 2px 8px #0F172A10" }}>
            <div className="flex items-center gap-2 min-w-0">
              <span className="w-3 h-3 rounded-full shrink-0 ring-2 ring-white dark:ring-gray-900 bg-slate-900" />
              <div className="min-w-0">
                <span className="font-semibold text-etex-gray-800 dark:text-gray-200 truncate block leading-tight">
                  Portfolio Average
                </span>
                <span className="flex items-center gap-1.5 text-[9px]">
                  <span className="text-etex-gray-500">{data.length} project{data.length !== 1 ? "s" : ""}</span>
                  <span className="text-etex-gray-300">·</span>
                  <span
                    className="font-semibold rounded-full px-1.5 py-px"
                    style={{
                      backgroundColor: `${BANDS[portfolioAvg.band].fill}26`,
                      color: BANDS[portfolioAvg.band].text,
                    }}
                  >
                    {BANDS[portfolioAvg.band].label}
                  </span>
                </span>
              </div>
            </div>
            <div className="flex items-center gap-3 shrink-0 flex-wrap">
              <div className="text-center">
                <span className="block text-[8px] uppercase tracking-wider text-etex-gray-400 font-semibold">Cost @ Risk</span>
                <span className="font-bold text-etex-gray-800 dark:text-gray-200">{portfolioAvg.cost}%</span>
              </div>
              <div className="text-center">
                <span className="block text-[8px] uppercase tracking-wider text-etex-gray-400 font-semibold">Time @ Risk</span>
                <span className="font-bold text-etex-gray-800 dark:text-gray-200">{portfolioAvg.time}%</span>
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
                <span className="flex items-center gap-1.5 text-[9px]">
                  <span className="font-medium" style={{ color: activeData.phaseColor }}>
                    {activeData.phaseLabel}
                  </span>
                  <span className="text-etex-gray-300">·</span>
                  <span
                    className="font-semibold rounded-full px-1.5 py-px"
                    style={{
                      backgroundColor: `${BANDS[activeData.bandIdx].fill}26`,
                      color: BANDS[activeData.bandIdx].text,
                    }}
                  >
                    {BANDS[activeData.bandIdx].label}
                  </span>
                </span>
              </div>
            </div>
            <div className="flex items-center gap-3 shrink-0 flex-wrap">
              <div className="text-center">
                <span className="block text-[8px] uppercase tracking-wider text-etex-gray-400 font-semibold">Cost @ Risk</span>
                <span className="font-bold text-etex-gray-800 dark:text-gray-200">
                  {activeData.clampedCost ? ">" : ""}{activeData.costPct}%
                </span>
                <span className="block text-[9px] text-etex-gray-400">
                  {formatCurrency(activeData.costKeur, { compact: true })}
                </span>
              </div>
              <div className="text-center">
                <span className="block text-[8px] uppercase tracking-wider text-etex-gray-400 font-semibold">Time @ Risk</span>
                <span className="font-bold text-etex-gray-800 dark:text-gray-200">
                  {activeData.clampedTime ? ">" : ""}{activeData.timePct}%
                </span>
                <span className="block text-[9px] text-etex-gray-400">
                  {activeData.timeDays}d
                </span>
              </div>
              <div className="text-center">
                <span className="block text-[8px] uppercase tracking-wider text-etex-gray-400 font-semibold">EAC</span>
                <span className="font-bold text-etex-gray-800 dark:text-gray-200">{formatCurrency(activeData.eac, { compact: true })}</span>
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
            Hover or click a bubble — outer rings = critical exposure
          </div>
        )}

        {noExposure > 0 && (
          <p className="text-[10px] text-etex-gray-400 mt-2">
            {noExposure} project{noExposure !== 1 ? "s" : ""} with no recorded exposure not shown
          </p>
        )}
      </div>
    </ExpandableWidget>
  );
});
