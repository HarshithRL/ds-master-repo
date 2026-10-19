"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import DOMPurify from "dompurify";
import { api } from "@/lib/api";
import { GATES } from "@/lib/constants";
import {
  cn,
  formatCurrency,
  formatDate,
  formatVariance,
  roundTo,
} from "@/lib/utils";
import { calcEAC, calcVariance, calcCPI, calcSPI } from "@/lib/calculations";
import type { ProjectWithRelations } from "@/types";
import {
  ArrowDown,
  ArrowUp,
  ArrowRight,
  Check,
  ImageDown,
  Printer,
} from "lucide-react";
import Link from "next/link";

/* ═══════════════════════════════════════════════════════════════════════
   Types
   ═══════════════════════════════════════════════════════════════════════ */

type RAGValue = "RED" | "AMBER" | "GREEN" | null | undefined;

type SnapshotData = {
  varianceAtCompletion: number | null;
  scheduleBuffer: number | null;
  periodLabel: string;
};

/* ═══════════════════════════════════════════════════════════════════════
   Helpers
   ═══════════════════════════════════════════════════════════════════════ */

const ragLabel = (v: RAGValue) =>
  v === "GREEN" ? "On Track" : v === "AMBER" ? "At Risk" : v === "RED" ? "Critical" : "Not Set";

const ragBg = (v: RAGValue) =>
  v === "GREEN"
    ? "bg-green-500"
    : v === "AMBER"
      ? "bg-amber-500"
      : v === "RED"
        ? "bg-red-500"
        : "bg-gray-400";

/* ═══════════════════════════════════════════════════════════════════════
   Gate Progression — linear stepper showing gate completion.
   A gate is considered passed if its own status is PASSED, or any later
   gate is PASSED (gates are linear: passing a later one implies the
   earlier ones are done).
   ═══════════════════════════════════════════════════════════════════════ */

function GateProgression({ gates }: { gates: ProjectWithRelations["gates"] }) {
  const safeGates = gates ?? [];
  const statusByKey = new Map<string, string>(safeGates.map((g) => [g.gate, g.status]));

  // Walk from the last gate backwards: once we find a PASSED one, every
  // earlier gate counts as passed too. Then the first non-passed gate is
  // "current"; everything after is "future".
  let lastPassedIdx = -1;
  for (let i = GATES.length - 1; i >= 0; i--) {
    if (statusByKey.get(GATES[i].key) === "PASSED") {
      lastPassedIdx = i;
      break;
    }
  }
  const currentIdx = lastPassedIdx + 1 < GATES.length ? lastPassedIdx + 1 : -1;

  return (
    <div className="w-full mt-2">
      {/* Mobile / md-down: compact segmented bar */}
      <div className="flex gap-0.5 rounded-md overflow-hidden h-7 sm:hidden">
        {GATES.map((gate, i) => {
          const passed = i <= lastPassedIdx;
          const current = i === currentIdx;
          return (
            <div
              key={gate.key}
              className={cn(
                "flex-1 flex items-center justify-center min-w-0 transition-all duration-300",
                current && "ring-2 ring-white shadow-lg z-10 rounded-sm",
              )}
              style={{
                backgroundColor: passed ? gate.color : "rgba(255,255,255,0.15)",
                opacity: passed ? 1 : current ? 0.95 : 0.55,
              }}
            >
              <span
                className={cn(
                  "text-[8px] font-bold leading-none truncate px-1",
                  passed ? "text-white drop-shadow-sm" : "text-white/80",
                )}
              >
                {gate.key.charAt(0)}
              </span>
            </div>
          );
        })}
      </div>

      {/* sm+ : stepper with circles, connecting line, and labels */}
      <div className="hidden sm:block relative">
        {/* Track aligned to circle centers (each circle is centered in its flex segment, so first/last sit at 1/2N from each edge) */}
        <div
          className="absolute top-3.5 h-1 bg-white/20 rounded-full"
          style={{
            left: `${50 / GATES.length}%`,
            right: `${50 / GATES.length}%`,
          }}
        />
        {lastPassedIdx > 0 && (
          <div
            className="absolute top-3.5 h-1 bg-white rounded-full transition-all duration-500"
            style={{
              left: `${50 / GATES.length}%`,
              width: `${(lastPassedIdx / (GATES.length - 1)) * (100 - 100 / GATES.length)}%`,
            }}
          />
        )}

        <div className="relative flex justify-between items-start">
          {GATES.map((gate, i) => {
            const passed = i <= lastPassedIdx;
            const current = i === currentIdx;
            return (
              <div
                key={gate.key}
                className="flex flex-col items-center min-w-0 flex-1"
              >
                <div
                  className={cn(
                    "w-7 h-7 rounded-full flex items-center justify-center shrink-0 transition-all duration-300 border-2",
                    current
                      ? "scale-110 shadow-lg ring-2 ring-white ring-offset-2 ring-offset-etex-orange"
                      : "",
                  )}
                  style={{
                    backgroundColor: passed ? gate.color : "rgba(255,255,255,0.15)",
                    borderColor: passed ? gate.color : "rgba(255,255,255,0.4)",
                  }}
                >
                  {passed ? (
                    <Check className="w-3.5 h-3.5 text-white" strokeWidth={3} />
                  ) : (
                    <span
                      className={cn(
                        "text-[10px] font-bold leading-none",
                        current ? "text-white" : "text-white/60",
                      )}
                    >
                      {i + 1}
                    </span>
                  )}
                </div>
                <span
                  className={cn(
                    "mt-1 text-[9px] font-semibold leading-none tracking-wide truncate max-w-full px-0.5",
                    passed
                      ? "text-white"
                      : current
                        ? "text-white"
                        : "text-white/50",
                  )}
                >
                  {gate.key}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════
   Completion Wheel (donut)
   ═══════════════════════════════════════════════════════════════════════ */

function CompletionWheel({ value, size = 70 }: { value: number; size?: number }) {
  const pct = Math.min(100, Math.max(0, value));
  const r = 28;
  const c = 2 * Math.PI * r;
  const offset = c - (pct / 100) * c;

  return (
    <div className="flex flex-col items-center gap-0.5 shrink-0">
      <div className="relative" style={{ width: size, height: size }}>
        <svg viewBox="0 0 70 70" className="w-full h-full -rotate-90">
          <circle cx="35" cy="35" r={r} fill="none" stroke="rgba(255,255,255,0.2)" strokeWidth="6" />
          <circle
            cx="35" cy="35" r={r}
            fill="none"
            stroke="#FFFFFF"
            strokeWidth="6"
            strokeLinecap="round"
            strokeDasharray={c}
            strokeDashoffset={offset}
            className="transition-all duration-700 ease-out"
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-base font-extrabold text-white leading-none">
            {roundTo(pct, 1)}%
          </span>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════
   Section Header — orange bar with white text
   ═══════════════════════════════════════════════════════════════════════ */

function SectionHeader({ title, className }: { title: string; className?: string }) {
  return (
    <div className={cn("section-header text-[11px] py-1.5 px-3", className)}>
      {title}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════
   Section Label — lightweight left-border accent label (no background)
   ═══════════════════════════════════════════════════════════════════════ */

function SectionLabel({ title }: { title: string }) {
  return (
    <div className="px-4 py-1.5 border-l-4 border-etex-orange">
      <span className="text-[11px] font-bold uppercase tracking-wider text-etex-orange">
        {title}
      </span>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════
   Status Indicator — dot + label + trend arrow (like reference)
   ═══════════════════════════════════════════════════════════════════════ */

function StatusIndicator({
  label,
  value,
  textValue,
  trend,
}: {
  label: string;
  value: RAGValue;
  textValue: string;
  trend?: "up" | "down" | "flat";
}) {
  const TrendIcon = trend === "up" ? ArrowUp : trend === "down" ? ArrowDown : ArrowRight;

  return (
    <div className="flex items-center justify-between px-3 py-2 border-b border-gray-200 last:border-b-0">
      <div className="flex items-center gap-2">
        <div className={cn("w-3 h-3 rounded-full shrink-0", ragBg(value))} />
        <span className="text-[11px] font-semibold uppercase tracking-wide text-gray-500">
          {label}
        </span>
      </div>
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium text-gray-700">{textValue}</span>
        <TrendIcon className="w-3.5 h-3.5 text-gray-400" />
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════
   KPI Cell — simple label + value in a bordered box
   ═══════════════════════════════════════════════════════════════════════ */

function KPICell({
  label,
  value,
  subLabel,
  valueColor,
  className,
}: {
  label: string;
  value: string;
  subLabel?: string;
  valueColor?: string;
  className?: string;
}) {
  return (
    <div className={cn("px-3 py-2 text-center", className)}>
      <div className="text-[9px] font-semibold uppercase tracking-wider text-gray-400 mb-0.5">
        {label}
      </div>
      <div
        className={cn("text-base font-bold leading-tight", valueColor || "text-gray-900")}
      >
        {value}
      </div>
      {subLabel && (
        <div className="text-[9px] text-gray-400 mt-0.5">{subLabel}</div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════
   Risk Quadrant — mini matrix with colored cells
   ═══════════════════════════════════════════════════════════════════════ */

// Columns: impact (low → very high). Rows: probability bands, bottom → top,
// with the top row reserved exclusively for 100%-probability items (issues).
const IMPACT_COLS = ["LOW", "MODERATE", "HIGH", "VERY_HIGH"] as const;
const PROB_ROWS = [
  { key: "0-20", label: "0-20%", test: (p: number) => p >= 0 && p <= 20 },
  { key: "21-50", label: "21-50%", test: (p: number) => p >= 21 && p <= 50 },
  { key: "51-80", label: "51-80%", test: (p: number) => p >= 51 && p <= 80 },
  { key: "81-99", label: "81-99%", test: (p: number) => p >= 81 && p <= 99 },
  { key: "100", label: "100%", test: () => true }, // issues row — matched by type, not probability
] as const;

// Cell heat: green (low-left) → red (high-right), intensifying toward the
// issues row at the top.
const RISK_CELL_COLORS: string[][] = [
  ["#10b981", "#10b981", "#10b981", "#FBBF24"], // 0-20%
  ["#10b981", "#FBBF24", "#FBBF24", "#EF4444"], // 21-50%
  ["#10b981", "#FBBF24", "#EF4444", "#EF4444"], // 51-80%
  ["#FBBF24", "#EF4444", "#EF4444", "#EF4444"], // 81-99%
  ["#991B1B", "#991B1B", "#991B1B", "#991B1B"], // 100% (issues)
];

function RiskQuadrant({ risks }: { risks: ProjectWithRelations["risks"] }) {
  const safeRisks = risks ?? [];
  const openRisks = safeRisks.filter((r) => r.status !== "CLOSED");

  // 5 rows × 4 cols. Row 4 (index 4, top) holds only issue-type items
  // (100% probability); rows 0-3 hold risk-type items by probability band.
  const matrix: number[][] = PROB_ROWS.map(() => IMPACT_COLS.map(() => 0));

  for (const r of openRisks) {
    const colIdx = IMPACT_COLS.indexOf(r.impact as (typeof IMPACT_COLS)[number]);
    if (colIdx === -1) continue;
    if (r.type === "ISSUE") {
      matrix[4][colIdx]++;
      continue;
    }
    const prob = r.probability ?? 50;
    const rowIdx = prob >= 100 ? 4 : prob >= 81 ? 3 : prob >= 51 ? 2 : prob >= 21 ? 1 : 0;
    matrix[rowIdx][colIdx]++;
  }

  const total = openRisks.length;
  const veryHighCount = openRisks.filter((r) => r.impact === "VERY_HIGH").length;
  const highCount = openRisks.filter((r) => r.impact === "HIGH").length;
  const moderateCount = openRisks.filter((r) => r.impact === "MODERATE").length;
  const lowCount = openRisks.filter((r) => r.impact === "LOW").length;

  return (
    <div className="flex gap-4">
      <div>
        <div className="text-[9px] font-bold uppercase text-gray-500 mb-1">Risk Quadrant</div>
        <div className="flex items-end gap-0.5">
          {/* Y-axis label */}
          <div className="flex flex-col items-center mr-0.5">
            <span className="text-[7px] text-gray-400 font-bold" style={{ writingMode: "vertical-lr", transform: "rotate(180deg)" }}>
              PROBABILITY
            </span>
          </div>
          <div className="flex flex-col gap-0.5">
            {/* Rows top (100% / issues) to bottom (0-20%) */}
            {[4, 3, 2, 1, 0].map((row) => (
              <div key={row} className="flex items-center gap-0.5">
                <div className="grid grid-cols-4 gap-0.5">
                  {IMPACT_COLS.map((_, col) => (
                    <div
                      key={col}
                      className="w-6 h-6 flex items-center justify-center text-[9px] font-bold rounded-sm"
                      style={{
                        backgroundColor: RISK_CELL_COLORS[row][col],
                        color: matrix[row][col] > 0 ? (row >= 3 ? "#FFFFFF" : "#374151") : "transparent",
                      }}
                    >
                      {matrix[row][col] || ""}
                    </div>
                  ))}
                </div>
                <span className="text-[6.5px] text-gray-400 font-semibold w-10 shrink-0">
                  {PROB_ROWS[row].label}
                </span>
              </div>
            ))}
          </div>
        </div>
        <div className="text-center text-[7px] text-gray-400 font-bold mt-0.5 ml-3">
          IMPACT — Low · Moderate · High · Very High
        </div>
      </div>
      <div className="flex flex-col gap-1 text-[10px] justify-center">
        <div>Total: <strong>{total}</strong></div>
        <div className="flex items-center gap-1">
          <div className="w-2.5 h-2.5 rounded-full bg-red-900" />
          Issues: {openRisks.filter((r) => r.type === "ISSUE").length}
        </div>
        <div className="flex items-center gap-1">
          <div className="w-2.5 h-2.5 rounded-full bg-red-700" />
          Very High: {veryHighCount}
        </div>
        <div className="flex items-center gap-1">
          <div className="w-2.5 h-2.5 rounded-full bg-red-500" />
          High: {highCount}
        </div>
        <div className="flex items-center gap-1">
          <div className="w-2.5 h-2.5 rounded-full bg-amber-400" />
          Moderate: {moderateCount}
        </div>
        <div className="flex items-center gap-1">
          <div className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
          Low: {lowCount}
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════
   Budget vs Schedule Variance Quadrant Chart
   ═══════════════════════════════════════════════════════════════════════ */

// Same CPI/SPI-index domain as the dashboard's CPI×SPI chart (cpi-spi-chart.tsx):
// fixed point at 1.0, x-axis = SPI (schedule), y-axis = CPI (budget). The visible
// plot domain (D_MIN..D_MAX) is tighter than the full valid range so values
// past it clamp to the edge rather than compressing the whole plot.
const VQ_MIN_INDEX = 0.3;
const VQ_MAX_INDEX = 2.0;
const VQ_D_MIN = 0.7;
const VQ_D_MAX = 1.3;

function VarianceQuadrant({ cpi, spi }: { cpi: number | null; spi: number | null }) {
  if (cpi == null || spi == null) {
    return (
      <div className="w-full flex items-center justify-center py-6 text-[10px] text-gray-400 italic">
        Insufficient data for variance quadrant
      </div>
    );
  }

  const clamp = (v: number) => Math.max(VQ_D_MIN, Math.min(VQ_D_MAX, v));
  const scale = (v: number) => 20 + ((clamp(v) - VQ_D_MIN) / (VQ_D_MAX - VQ_D_MIN)) * 80;

  const cx = scale(spi);
  const cy = 120 - scale(cpi); // Y inverted: higher CPI plots higher up

  const outOfDomain =
    spi < VQ_D_MIN || spi > VQ_D_MAX || cpi < VQ_D_MIN || cpi > VQ_D_MAX;
  const outOfValidRange =
    spi < VQ_MIN_INDEX || spi > VQ_MAX_INDEX || cpi < VQ_MIN_INDEX || cpi > VQ_MAX_INDEX;

  return (
    <div className="w-full">
      <svg viewBox="0 0 140 130" className="w-full">
        {/* Quadrant backgrounds, split at SPI=1 / CPI=1 */}
        <rect x="20" y="20" width="40" height="40" fill="#DCFCE7" /> {/* top-left: behind sched, under budget */}
        <rect x="60" y="20" width="40" height="40" fill="#BBF7D0" /> {/* top-right: ahead sched, under budget (best) */}
        <rect x="20" y="60" width="40" height="40" fill="#FECACA" /> {/* bottom-left: behind sched, over budget (worst) */}
        <rect x="60" y="60" width="40" height="40" fill="#FED7AA" /> {/* bottom-right: ahead sched, over budget */}

        {/* Grid lines at SPI=1 / CPI=1 */}
        <line x1="60" y1="20" x2="60" y2="100" stroke="#D1D5DB" strokeWidth="0.5" />
        <line x1="20" y1="60" x2="100" y2="60" stroke="#D1D5DB" strokeWidth="0.5" />

        {/* Quadrant labels */}
        <text x="40" y="10" textAnchor="middle" fontSize="5" fontWeight="600" fill="#6B7280">Behind Sched.</text>
        <text x="40" y="16" textAnchor="middle" fontSize="5" fontWeight="600" fill="#6B7280">Under Budget</text>
        <text x="100" y="10" textAnchor="middle" fontSize="5" fontWeight="600" fill="#6B7280">Ahead of Sched.</text>
        <text x="100" y="16" textAnchor="middle" fontSize="5" fontWeight="600" fill="#6B7280">Under Budget</text>
        <text x="40" y="108" textAnchor="middle" fontSize="5" fontWeight="600" fill="#6B7280">Behind Sched.</text>
        <text x="40" y="114" textAnchor="middle" fontSize="5" fontWeight="600" fill="#6B7280">Over Budget</text>
        <text x="100" y="108" textAnchor="middle" fontSize="5" fontWeight="600" fill="#6B7280">Ahead of Sched.</text>
        <text x="100" y="114" textAnchor="middle" fontSize="5" fontWeight="600" fill="#6B7280">Over Budget</text>

        {/* Axis labels */}
        <text x="60" y="125" textAnchor="middle" fontSize="5" fill="#9CA3AF">SPI (Schedule)</text>
        <text x="12" y="60" textAnchor="middle" fontSize="5" fill="#9CA3AF" transform="rotate(-90, 12, 60)">CPI (Budget)</text>

        {/* Data point — outward triangle when the exact value falls outside the visible domain */}
        {outOfDomain ? (
          <polygon
            points={`${cx},${cy - 6} ${cx - 5},${cy + 4} ${cx + 5},${cy + 4}`}
            fill="#1A1A2E"
            stroke="#E8713A"
            strokeWidth="1.5"
          />
        ) : (
          <circle cx={cx} cy={cy} r="5" fill="#1A1A2E" stroke="#E8713A" strokeWidth="2" />
        )}
        <text x={cx} y={cy - 8} textAnchor="middle" fontSize="6" fontWeight="700" fill="#1A1A2E">
          {spi.toFixed(2)} / {cpi.toFixed(2)}
        </text>
      </svg>
      {outOfValidRange && (
        <div className="text-center text-[8px] text-gray-400 italic mt-0.5">
          Index outside the typical {VQ_MIN_INDEX.toFixed(1)}–{VQ_MAX_INDEX.toFixed(1)} range
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════
   Main One-Pager Component
   ═══════════════════════════════════════════════════════════════════════ */

export function ProjectOnePager({ projectId }: { projectId: string }) {
  const [project, setProject] = useState<ProjectWithRelations | null>(null);
  const [snapshot, setSnapshot] = useState<SnapshotData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exportingImage, setExportingImage] = useState(false);
  const onePagerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    Promise.all([
      api.get<ProjectWithRelations>(`/api/projects/${projectId}`),
      api
        .get<SnapshotData[]>(`/api/projects/${projectId}/snapshots`)
        .then((s) => (s.length > 0 ? s[0] : null))
        .catch(() => null),
    ])
      .then(([p, s]) => {
        setProject(p);
        setSnapshot(s);
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Failed to load project"),
      )
      .finally(() => setLoading(false));
  }, [projectId]);

  const budget = project?.budget;
  const bac = budget?.bac ?? 0;
  const eac = budget ? calcEAC(budget) : 0;
  const actuals = budget?.actuals ?? 0;
  const committed = budget?.committed ?? 0;
  const contingency = (budget?.riskContingencyBudgeted ?? 0) + (budget?.mgmtContingencyBudgeted ?? 0);
  const vac = budget ? calcVariance(budget) : 0;
  const vacPrev = snapshot?.varianceAtCompletion ?? null;
  const deltaVac = vacPrev !== null ? vac - vacPrev : null;
  const actPlanned = bac !== 0 ? roundTo((actuals / bac) * 100) : 0;

  const stakeholderNames = (role: "SPONSOR" | "OWNER" | "PROJECT_MANAGER") =>
    project?.assignments
      ?.filter((a) => a.role === role)
      .map((a) => a.user.name)
      .join(", ") || null;
  const sponsorNames = stakeholderNames("SPONSOR");
  const ownerNames = stakeholderNames("OWNER");
  const pmNames = stakeholderNames("PROJECT_MANAGER");

  const topRisks = useMemo(() => {
    if (!project) return [];
    return [...(project.risks ?? [])]
      .filter((r) => r.status !== "CLOSED" && r.type === "RISK")
      .sort((a, b) => (b.weight ?? 0) - (a.weight ?? 0))
      .slice(0, 5);
  }, [project]);

  const scopeChanges = project?.scopeChanges ?? [];
  const openIssues = (project?.risks ?? []).filter((r) => r.type === "ISSUE" && r.status !== "CLOSED").length;

  const scheduleBuffer = project?.scheduleBuffer ?? 0;

  // CPI/SPI for the variance quadrant — same formulas as the dashboard's CPI×SPI chart.
  const cpi = budget ? calcCPI(budget) : null;
  const spi = project ? calcSPI(project) : null;

  // Schedule performance KPIs (manual inputs)
  const denomGW = project?.daysGreenToWhite ?? 0;
  const svac =
    project?.totalFloatInclBuffer != null && denomGW > 0
      ? (project.totalFloatInclBuffer / denomGW) * 100
      : null;
  const svacPrev =
    project?.totalFloatInclBufferPrev != null && denomGW > 0
      ? (project.totalFloatInclBufferPrev / denomGW) * 100
      : null;
  const svacDelta = svac != null && svacPrev != null ? svac - svacPrev : null;

  // Contingencies/Issues/Buffer summary
  const riskCostImpactProb = useMemo(() => {
    if (!project) return 0;
    return (project.risks ?? [])
      .filter((r) => r.type === "RISK" && r.status !== "CLOSED")
      .reduce((sum, r) => sum + (r.costImpact ?? 0) * ((r.probability ?? 50) / 100), 0);
  }, [project]);

  const totalRiskCost = useMemo(() => {
    if (!project) return 0;
    return (project.risks ?? [])
      .filter((r) => r.type === "RISK" && r.status !== "CLOSED")
      .reduce((sum, r) => sum + (r.costImpact ?? 0), 0);
  }, [project]);

  const maxRiskDelay = useMemo(() => {
    if (!project) return 0;
    return Math.max(0, ...(project.risks ?? [])
      .filter((r) => r.type === "RISK" && r.status !== "CLOSED")
      .map((r) => r.timeImpact ?? 0));
  }, [project]);

  const riskDelayWeighted = useMemo(() => {
    if (!project) return 0;
    return (project.risks ?? [])
      .filter((r) => r.type === "RISK" && r.status !== "CLOSED")
      .reduce((sum, r) => sum + (r.timeImpact ?? 0) * ((r.probability ?? 50) / 100), 0);
  }, [project]);

  /**
   * Renders the one-pager to a single tall PNG instead of paginating it —
   * sidesteps print CSS entirely, so nothing is squished/clipped to fit a
   * fixed page size regardless of how much content the project has.
   */
  /**
   * Renders the one-pager to a single tall PNG instead of paginating it.
   *
   * The live node sits inside the app shell's scroll chain
   * (<div class="h-screen overflow-hidden"> > <main class="overflow-y-auto">,
   * see src/components/layout/app-shell.tsx) — capturing it in place only
   * grabs whatever width/height it's currently laid out at inside that
   * scrolling viewport, not the full content. So instead we clone the node,
   * detach it from that scroll chain entirely by appending the clone
   * directly to <body> (off-screen), pin it to the full design width, strip
   * any overflow clipping on the clone and its descendants, let it reflow,
   * measure the resulting full height, and capture *that* — independent of
   * the live viewport/scroll state.
   */
  const handleSaveImage = async () => {
    const node = onePagerRef.current;
    if (!node || exportingImage) return;
    setExportingImage(true);

    const EXPORT_WIDTH = 1400; // matches the onepager-root's max-w-[1400px]
    let clone: HTMLElement | null = null;
    try {
      // html-to-image (SVG foreignObject + data-URI) rendered a blank page
      // here — its rasteriser chokes on the color-mix()/oklch() color
      // functions Tailwind v4 emits throughout globals.css, and fails
      // silently instead of throwing. html2canvas-pro walks the DOM and
      // redraws it with the Canvas 2D API directly (the same fundamental
      // approach the working PDF/print path relies on — real layout, not a
      // serialized snapshot) and explicitly supports those color functions.
      const { default: html2canvas } = await import("html2canvas-pro");

      clone = node.cloneNode(true) as HTMLElement;
      clone.style.position = "fixed";
      clone.style.top = "0";
      clone.style.left = "-99999px";
      clone.style.margin = "0";
      clone.style.width = `${EXPORT_WIDTH}px`;
      clone.style.maxWidth = "none";
      clone.style.height = "auto";
      clone.style.maxHeight = "none";
      clone.style.overflow = "visible";
      clone.querySelectorAll(".onepager-print-hidden").forEach((el) => el.remove());
      // Neutralise any scroll wrappers nested inside (e.g. the Top 5 Risks
      // table's horizontal scroll on small screens) so nothing is clipped
      // in the export regardless of how it behaves in the live layout.
      clone.querySelectorAll<HTMLElement>(".overflow-x-auto, .overflow-y-auto, .overflow-auto, .overflow-hidden").forEach((el) => {
        el.style.overflow = "visible";
        el.style.maxHeight = "none";
      });
      document.body.appendChild(clone);

      // Two rAFs: one to commit the width/overflow changes, one to let
      // layout fully settle before measuring scrollHeight.
      await new Promise<void>((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
      );

      const height = clone.scrollHeight;
      clone.style.height = `${height}px`;

      const canvas = await html2canvas(clone, {
        backgroundColor: "#ffffff",
        scale: 2,
        width: EXPORT_WIDTH,
        height,
        windowWidth: EXPORT_WIDTH,
        windowHeight: height,
      });

      const link = document.createElement("a");
      const safeName = (project?.name || "project").replace(/[^a-z0-9]+/gi, "-").toLowerCase();
      link.download = `${safeName}-one-pager.png`;
      link.href = canvas.toDataURL("image/png");
      link.click();
    } catch (err) {
      console.error("Failed to export one-pager image:", err);
    } finally {
      if (clone) document.body.removeChild(clone);
      setExportingImage(false);
    }
  };

  if (loading) {
    return (
      <div className="max-w-[1400px] mx-auto p-4">
        <div className="animate-pulse space-y-4">
          <div className="h-24 bg-gray-200 rounded-lg" />
          <div className="grid grid-cols-2 gap-4">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="h-40 bg-gray-200 rounded-lg" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (error || !project) {
    return (
      <div className="max-w-[1400px] mx-auto p-6 text-center">
        <p className="text-red-600 font-medium">{error || "Project not found"}</p>
        <Link href="/projects" className="text-sm text-etex-orange hover:underline mt-2 inline-block">
          Back to projects
        </Link>
      </div>
    );
  }

  return (
    <div ref={onePagerRef} className="max-w-[1400px] mx-auto onepager-root">
      {/* ═══════════════════ HEADER — Orange bar ═══════════════════ */}
      <div className="bg-gradient-to-r from-etex-orange to-etex-orange-dark rounded-t-lg px-4 sm:px-6 py-4 print:rounded-none">
        {/* Row 1: Name + completion + export */}
        <div className="flex items-center justify-between gap-4 mb-3">
          <div className="flex-1 min-w-0">
            <h1 className="text-xl sm:text-2xl font-extrabold text-white tracking-tight truncate">
              {project.name}
            </h1>
            <div className="flex items-center gap-2 text-[11px] text-white/70 flex-wrap mt-0.5">
              <span>Project ID: {project.reference || "—"}</span>
              {project.factory && <span>| {project.factory.name}</span>}
              <span>| {formatDate(project.updatedAt)}</span>
            </div>
          </div>

          <div className="flex items-center gap-4 shrink-0">
            <CompletionWheel value={project.progress} />
            <div className="flex flex-col gap-1.5 onepager-print-hidden">
              <button
                onClick={() => window.print()}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-white/15 hover:bg-white/25 text-white text-[11px] font-medium transition-colors cursor-pointer"
              >
                <Printer className="w-3.5 h-3.5" />
                PDF
              </button>
              <button
                onClick={handleSaveImage}
                disabled={exportingImage}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-white/15 hover:bg-white/25 text-white text-[11px] font-medium transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-wait"
              >
                <ImageDown className="w-3.5 h-3.5" />
                {exportingImage ? "Saving…" : "Image"}
              </button>
            </div>
          </div>
        </div>

        {/* Row 2: Gate progression — full width */}
        <GateProgression gates={project.gates ?? []} />
      </div>

      {/* ═══════════════════ BODY ═══════════════════ */}
      <div className="bg-white border border-t-0 border-gray-200 rounded-b-lg print:border-0">

        {/* ── Description (left) | Status Indicators (right) ── */}
        <div className="grid grid-cols-1 lg:grid-cols-2 border-b border-gray-200">
          {/* Left: Description + Stakeholders */}
          <div className="border-r-0 lg:border-r border-gray-200">
            <SectionLabel title="Project Description" />
            <div className="px-4 py-2.5 text-xs text-gray-600 leading-relaxed">
              {project.description || <span className="italic text-gray-400">No description provided</span>}
            </div>
            <div className="grid grid-cols-3 divide-x divide-gray-100 border-t border-gray-100">
              {[
                { label: "Sponsor", name: sponsorNames },
                { label: "Owner", name: ownerNames },
                { label: "PM", name: pmNames },
              ].map((s) => (
                <div key={s.label} className="px-3 py-2">
                  <div className="text-[9px] font-semibold uppercase tracking-wider text-gray-400">
                    {s.label}
                  </div>
                  <div className="text-xs font-medium text-gray-800 truncate mt-0.5">
                    {s.name || "—"}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Right: Status Indicators — 6 manual RAG dots + free-text labels */}
          <div>
            <SectionLabel title="Project Status Indicators" />
            <div className="grid grid-cols-3 divide-x divide-gray-100">
              <StatusIndicator label="Overall"  value={project.ragProgress}  textValue={project.ragProgressLabel || ragLabel(project.ragProgress)} />
              <StatusIndicator label="Scope"    value={project.ragScope}     textValue={project.ragScopeLabel || ragLabel(project.ragScope)} />
              <StatusIndicator label="Schedule" value={project.ragSchedule}  textValue={project.ragScheduleLabel || ragLabel(project.ragSchedule)} />
            </div>
            <div className="grid grid-cols-3 divide-x divide-gray-100 border-t border-gray-100">
              <StatusIndicator label="Cost"      value={project.ragCost}      textValue={project.ragCostLabel || ragLabel(project.ragCost)} />
              <StatusIndicator label="Resources" value={project.ragResources} textValue={project.ragResourcesLabel || ragLabel(project.ragResources)} />
              <StatusIndicator label="Risks"     value={project.ragRisk}      textValue={project.ragRiskLabel || ragLabel(project.ragRisk)} />
            </div>
          </div>
        </div>

        {/* ── Business Case (top-line investment metrics) ── */}
        {(project.totalCost != null || project.expectedValue != null || project.roi != null || project.paybackYears != null) && (
          <div className="border-b border-gray-200">
            <SectionLabel title="Business Case" />
            <div className="grid grid-cols-2 sm:grid-cols-4 divide-x divide-gray-100">
              <KPICell label="Total Cost" value={project.totalCost != null ? formatCurrency(project.totalCost) : "—"} subLabel="Investment" />
              <KPICell label="Expected Value" value={project.expectedValue != null ? formatCurrency(project.expectedValue) : "—"} subLabel="Lifetime NPV" />
              <KPICell label="ROI" value={project.roi != null ? `${roundTo(project.roi)}%` : "—"} valueColor={project.roi != null && project.roi >= 100 ? "text-emerald-600" : undefined} />
              <KPICell label="Payback" value={project.paybackYears != null ? `${roundTo(project.paybackYears, 1)} yr` : "—"} />
            </div>
          </div>
        )}

        {/* ── Side-by-side: Financial Performance | Schedule Performance ── */}
        <div className="grid grid-cols-1 lg:grid-cols-2 border-b border-gray-200">
          {/* Financial Performance */}
          <div className="border-r-0 lg:border-r border-gray-200">
            <SectionHeader title="Financial Performance" />
            <div className="grid grid-cols-2 sm:grid-cols-4 divide-x divide-gray-100 border-b border-gray-100">
              <KPICell label="BAC" value={formatCurrency(bac)} subLabel="Budget" />
              <KPICell label="EAC" value={formatCurrency(eac)} subLabel="Estimate" />
              <KPICell label="Cont." value={formatCurrency(contingency)} subLabel="Contingency" />
              {(() => {
                const vacFmt = formatVariance(vac);
                return (
                  <KPICell
                    label="VAC"
                    value={vacFmt.display}
                    subLabel="Variance"
                    valueColor={vacFmt.sentiment === "positive" ? "text-emerald-600" : "text-red-600"}
                  />
                );
              })()}
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 divide-x divide-gray-100">
              <KPICell label="Actuals" value={formatCurrency(actuals)} />
              <KPICell label="Committed" value={formatCurrency(committed)} />
              <KPICell label="Act/Plan" value={`${actPlanned}%`} />
              {(() => {
                const deltaFmt = formatVariance(deltaVac);
                return (
                  <KPICell
                    label="Delta VAC"
                    value={deltaFmt.display}
                    subLabel={snapshot?.periodLabel ? "vs prev." : undefined}
                    valueColor={
                      deltaFmt.sentiment === "positive" ? "text-emerald-600"
                        : deltaFmt.sentiment === "negative" ? "text-red-600" : undefined
                    }
                  />
                );
              })()}
            </div>
          </div>

          {/* Schedule Performance */}
          <div>
            <SectionHeader title="Schedule Performance" />
            <div className="grid grid-cols-3 sm:grid-cols-6 divide-x divide-gray-100 border-b border-gray-100">
              <KPICell
                label="Float excl."
                value={project.totalFloatExclBuffer != null ? `${project.totalFloatExclBuffer}d` : "—"}
                subLabel="No buffer"
              />
              <KPICell
                label="Float incl."
                value={project.totalFloatInclBuffer != null ? `${project.totalFloatInclBuffer}d` : "—"}
                subLabel="With buffer"
              />
              <KPICell
                label="SVAC"
                value={svac != null ? `${roundTo(svac)}%` : "—"}
                subLabel="Schedule var."
                valueColor={svac == null ? undefined : svac >= 0 ? "text-emerald-600" : "text-red-600"}
              />
              <KPICell
                label="ΔSVAC"
                value={svacDelta != null ? `${svacDelta > 0 ? "+" : ""}${roundTo(svacDelta)}%` : "—"}
                subLabel="vs prev."
                valueColor={svacDelta == null ? undefined : svacDelta >= 0 ? "text-emerald-600" : "text-red-600"}
              />
              <KPICell
                label="Buffer"
                value={`${scheduleBuffer}d`}
                subLabel="Plan − Exp."
                valueColor={scheduleBuffer < 0 ? "text-red-600" : "text-emerald-600"}
              />
              <KPICell
                label="Res %"
                value={project.resourceConsumptionPct != null ? `${roundTo(project.resourceConsumptionPct)}%` : "—"}
                subLabel="Consumption"
              />
            </div>
            {/* Variance Quadrant Chart */}
            <div className="flex items-center justify-center py-2 px-4">
              <div className="w-full max-w-60">
                <VarianceQuadrant cpi={cpi} spi={spi} />
              </div>
            </div>
          </div>
        </div>

        {/* ── Side-by-side: Risk/Issues | Achievements + Actions ── */}
        <div className="grid grid-cols-1 lg:grid-cols-2 border-b border-gray-200">
          {/* Left: Contingencies & Issues + Risk Quadrant */}
          <div className="border-r-0 lg:border-r border-gray-200">
            <SectionLabel title="Contingencies & Issues" />
            <div className="grid grid-cols-3 divide-x divide-gray-100 border-b border-gray-100">
              <div className="px-3 py-2.5">
                <div className="text-[9px] text-gray-400 mb-0.5">Risk Cost x Prob</div>
                <div className="text-sm font-bold text-gray-800">
                  {formatCurrency(riskCostImpactProb)}
                </div>
                <div className="text-[9px] text-gray-400 mt-1.5">Total Risk Cost</div>
                <div className="text-sm font-bold text-gray-800">
                  {formatCurrency(totalRiskCost)}
                </div>
              </div>
              <div className="px-3 py-2.5">
                <div className="text-[9px] text-gray-400 mb-0.5">Issues Open</div>
                <div className="text-sm font-bold text-gray-800">{openIssues}</div>
              </div>
              <div className="px-3 py-2.5">
                <div className="text-[9px] text-gray-400 mb-0.5">Risk Delay x Prob</div>
                <div className="text-sm font-bold text-gray-800">
                  {roundTo(riskDelayWeighted)} Days
                </div>
                <div className="text-[9px] text-gray-400 mt-1.5">Max Risk Delay</div>
                <div className="text-sm font-bold text-gray-800">{maxRiskDelay} Days</div>
              </div>
            </div>
            <div className="px-4 py-3">
              <RiskQuadrant risks={project.risks ?? []} />
            </div>
          </div>

          {/* Right: Key Achievements + Planned Actions */}
          <div>
            <SectionLabel title="Key Achievements" />
            <div className="px-4 py-2.5 border-b border-gray-100">
              {project.keyAchievements ? (
                <div
                  className="text-xs text-gray-600 leading-relaxed [&_ul]:list-disc [&_ul]:pl-4 [&_li]:mb-0.5"
                  dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(project.keyAchievements) }}
                />
              ) : (
                <span className="text-xs text-gray-400 italic">No achievements recorded</span>
              )}
            </div>

            {(project.plannedActions?.length ?? 0) > 0 && (
              <>
                <SectionLabel title="Planned Actions" />
                <table className="w-full text-[10px]">
                  <thead>
                    <tr className="bg-gray-50/80 border-b border-gray-100">
                      <th className="text-left px-3 py-1.5 font-semibold text-gray-500 uppercase tracking-wider">Action</th>
                      <th className="text-center px-2 py-1.5 font-semibold text-gray-500 uppercase tracking-wider">Owner</th>
                      <th className="text-center px-2 py-1.5 font-semibold text-gray-500 uppercase tracking-wider">By</th>
                    </tr>
                  </thead>
                  <tbody>
                    {project.plannedActions
                      .filter((a) => a.status !== "CANCELLED")
                      .slice(0, 5)
                      .map((a) => (
                        <tr key={a.id} className="border-b border-gray-100 last:border-b-0">
                          <td className="px-3 py-1.5 text-gray-700 truncate max-w-50">{a.action}</td>
                          <td className="px-2 py-1.5 text-center text-gray-500">{a.ownerLabel || "—"}</td>
                          <td className="px-2 py-1.5 text-center text-gray-500">{a.byDate ? formatDate(a.byDate) : "—"}</td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </>
            )}
          </div>
        </div>

        {/* ═══════════════════ TOP 5 RISKS — full width ═══════════════════ */}
        <div className="border-b border-gray-200">
          <div className="bg-red-600 text-white text-[11px] font-bold uppercase tracking-wider px-4 py-1.5">
            Top 5 Risks
          </div>
          <div className="overflow-x-auto print:overflow-visible">
            <table className="w-full text-[10px] min-w-[500px] print:min-w-0">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left px-3 py-1.5 font-semibold text-gray-500 uppercase tracking-wider">Risk</th>
                  <th className="text-center px-2 py-1.5 font-semibold text-gray-500 uppercase tracking-wider w-20">Severity</th>
                  <th className="text-right px-2 py-1.5 font-semibold text-gray-500 uppercase tracking-wider w-28">Risk Cost</th>
                  <th className="text-right px-2 py-1.5 font-semibold text-gray-500 uppercase tracking-wider w-24">Mitigation</th>
                </tr>
              </thead>
              <tbody>
                {topRisks.length === 0 && (
                  <tr>
                    <td colSpan={4} className="px-3 py-3 text-center text-gray-400 italic">
                      No open risks
                    </td>
                  </tr>
                )}
                {topRisks.map((r) => (
                  <tr key={r.id} className="border-b border-gray-100 last:border-b-0">
                    <td className="px-3 py-1.5 text-gray-700 truncate max-w-100">
                      {r.riskStatement}
                    </td>
                    <td className="px-2 py-1.5 text-center">
                      <span
                        className={cn(
                          "px-1.5 py-0.5 rounded-sm text-[9px] font-bold",
                          r.impact === "VERY_HIGH"
                            ? "bg-red-200 text-red-900"
                            : r.impact === "HIGH"
                              ? "bg-red-100 text-red-700"
                              : r.impact === "MODERATE"
                                ? "bg-amber-100 text-amber-700"
                                : "bg-emerald-100 text-emerald-700",
                        )}
                      >
                        {r.impact}
                      </span>
                    </td>
                    <td className="px-2 py-1.5 text-right text-gray-600">
                      {r.costImpact ? formatCurrency(r.costImpact) : "—"}
                    </td>
                    <td className="px-2 py-1.5 text-right text-gray-600">
                      {r.counterMeasures ? "Yes" : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* ── Scope Changes (full width, if any) ── */}
        {scopeChanges.length > 0 && (
          <div className="border-b border-gray-200">
            <SectionLabel title="Scope Changes" />
            <table className="w-full text-[10px]">
              <thead>
                <tr className="bg-gray-50/80 border-b border-gray-100">
                  <th className="text-left px-3 py-1.5 font-semibold text-gray-500 uppercase tracking-wider">Type</th>
                  <th className="text-center px-2 py-1.5 font-semibold text-gray-500 uppercase tracking-wider">Qty</th>
                  <th className="text-center px-2 py-1.5 font-semibold text-gray-500 uppercase tracking-wider">In Evaluation</th>
                  <th className="text-center px-2 py-1.5 font-semibold text-gray-500 uppercase tracking-wider">Approved</th>
                </tr>
              </thead>
              <tbody>
                <tr className="border-b border-gray-100">
                  <td className="px-3 py-1.5 text-gray-600">Cost Impact</td>
                  <td className="px-2 py-1.5 text-center font-medium">{scopeChanges.filter((s) => s.impactCost).length}</td>
                  <td className="px-2 py-1.5 text-center text-etex-orange font-medium">
                    {formatCurrency(scopeChanges.filter((s) => s.status === "OPEN" && s.impactCost).reduce((sum, s) => sum + (parseFloat(String(s.impactCost)) || 0), 0))}
                  </td>
                  <td className="px-2 py-1.5 text-center text-etex-orange font-medium">
                    {formatCurrency(scopeChanges.filter((s) => s.status !== "OPEN" && s.impactCost).reduce((sum, s) => sum + (parseFloat(String(s.impactCost)) || 0), 0))}
                  </td>
                </tr>
                <tr>
                  <td className="px-3 py-1.5 text-gray-600">Time Impact</td>
                  <td className="px-2 py-1.5 text-center font-medium">{scopeChanges.filter((s) => s.impactSchedule).length}</td>
                  <td className="px-2 py-1.5 text-center text-etex-orange font-medium">
                    {scopeChanges.filter((s) => s.status === "OPEN" && s.impactSchedule).reduce((sum, s) => sum + (parseFloat(String(s.impactSchedule)) || 0), 0)} Days
                  </td>
                  <td className="px-2 py-1.5 text-center text-etex-orange font-medium">
                    {scopeChanges.filter((s) => s.status !== "OPEN" && s.impactSchedule).reduce((sum, s) => sum + (parseFloat(String(s.impactSchedule)) || 0), 0)} Days
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        )}

        {/* ═══════════════════ FOOTER ═══════════════════ */}
        <div className="px-4 py-2 border-t border-gray-200 flex items-center justify-between text-[10px] text-gray-400">
          <span>
            Generated {new Date().toLocaleDateString("en-GB")} | {project.name}{project.reference ? ` | ${project.reference}` : ""}
          </span>
          <Link
            href={`/projects/${project.id}`}
            className="text-etex-orange hover:underline font-medium onepager-print-hidden"
          >
            View full project details &rarr;
          </Link>
        </div>
      </div>
    </div>
  );
}
