"use client";

import { useState, useRef } from "react";
import { cn, formatAmount, formatCurrency, formatVariance } from "@/lib/utils";
import {
  calcActualsCommitted,
  calcETC,
  calcEAC,
  calcVariance,
  calcVariancePct,
  calcOverspend,
  pctOfBac,
} from "@/lib/calculations";
import { AutoAmount, RowLabel } from "@/components/ui/auto-fields";
import { InfoHint } from "@/components/ui/info-hint";
import { useOptimisticRecord } from "@/hooks/use-optimistic-record";
import type { Budget } from "@/lib/db/models";

/* ═══════════════════════════════════════════════════════════════════
   Budget chart — standardized vocabulary
   ───────────────────────────────────────────────────────────────────
   Actuals    = already spent (editable)
   Committed  = locked-in commitments / POs (editable)
   Expected   = forecast remaining, not yet committed (editable)
   BAC        = Budget at Completion (target — outer ring = 100%)
   ETC        = Committed + Expected (Estimate to Complete)
   EAC        = Actuals + Committed + Expected (Estimate at Completion)
   VAC        = BAC − EAC (positive ⇒ under budget)
   Overspend  = max(0, EAC − BAC) — shown on the inner ring when EAC > BAC
   ═══════════════════════════════════════════════════════════════════ */

type SliceKey = "actuals" | "committed" | "expected" | "savings" | "overspend";

const SLICE_COLORS: Record<SliceKey, string> = {
  actuals: "var(--color-success, #10B981)",
  committed: "#E8713A" /* etex-orange */,
  expected: "#F4A261" /* etex-orange-light */,
  savings: "#B7E1CD" /* mint — unfilled BAC = forecast savings */,
  overspend: "var(--color-danger, #DC2626)",
};

const SLICE_LABELS: Record<SliceKey, string> = {
  actuals: "Actuals",
  committed: "Committed",
  expected: "Expected",
  savings: "Savings",
  overspend: "Overrun",
};

/* Hover groups: every row on the Summary table maps to one of these. The chart
   knows which arcs to highlight for each, so hover sync works in both directions.
   Single-slice groups (actuals/committed/expected/savings/overspend) also stand
   in as their own hover key — keeps the wheel's onMouseEnter handlers trivial. */
type HoverGroup = SliceKey | "ac" | "etc" | "eac" | "bac";

const HOVER_TO_SLICES: Record<HoverGroup, SliceKey[]> = {
  actuals: ["actuals"],
  committed: ["committed"],
  expected: ["expected"],
  savings: ["savings"],
  overspend: ["overspend"],
  ac: ["actuals", "committed"],
  etc: ["committed", "expected"],
  eac: ["actuals", "committed", "expected"],
  bac: ["actuals", "committed", "expected", "savings"],
};

/* ── Computed (read-only) value — grey background row ────────────── */

function ComputedAmount({
  value,
  unit = "k€",
  sentiment,
  variance = false,
}: {
  value: number | null | undefined;
  unit?: string;
  sentiment?: "positive" | "negative" | "neutral";
  /** Variance mode: positive (incl. rounded-to-zero) = good (green). */
  variance?: boolean;
}) {
  const v = variance ? formatVariance(value, { suffix: "" }) : null;
  const effSentiment = v?.sentiment ?? sentiment;
  const color =
    effSentiment === "positive"
      ? "text-success"
      : effSentiment === "negative"
        ? "text-danger"
        : "text-etex-gray-600";

  const display = v
    ? v.display
    : value == null
      ? "—"
      : formatCurrency(value, { signed: sentiment === "positive", suffix: "" });

  return (
    <div className="h-9 flex items-center justify-end gap-1.5 px-2.5">
      <span className={cn("text-sm font-mono font-medium tabular-nums", color)}>{display}</span>
      <span className="text-[10px] text-muted-foreground font-semibold tracking-wide">{unit}</span>
    </div>
  );
}

/* ── BudgetWheel ───────────────────────────────────────────────────
   Outer ring = BAC (100% circumference). Actuals → Committed → Expected
   stack sequentially and are capped at BAC. Any portion of EAC that
   exceeds BAC appears on a smaller inner ring as a single "Overspend"
   arc, scaled against BAC (so half the inner ring = 50% over budget).
   Hovering a segment highlights its legend row and vice versa.
   ──────────────────────────────────────────────────────────────── */

function BudgetWheel({
  actuals,
  committed,
  expected,
  eac,
  bac,
  hovered,
  onHover,
  size = 168,
}: {
  actuals: number;
  committed: number;
  expected: number;
  eac: number;
  bac: number;
  hovered: HoverGroup | null;
  onHover: (k: HoverGroup | null) => void;
  size?: number;
}) {
  const STROKE_OUTER = 16;
  const STROKE_INNER = 10;
  const RING_GAP = 5;

  const a = Math.max(0, actuals);
  const co = Math.max(0, committed);
  const exp = Math.max(0, expected);
  const overspend = Math.max(0, eac - bac);
  const savings = Math.max(0, bac - eac);

  // Sequential fill within BAC for the outer ring.
  const aFill = Math.min(a, bac);
  const coFill = Math.min(co, Math.max(0, bac - aFill));
  const expFill = Math.min(exp, Math.max(0, bac - aFill - coFill));

  const eacPct = pctOfBac(eac, bac);
  const isOverspend = overspend > 0;

  const cx = size / 2;
  const cy = size / 2;
  const rOuter = (size - STROKE_OUTER) / 2 - 2;
  const rInner = rOuter - STROKE_OUTER / 2 - RING_GAP - STROKE_INNER / 2;
  const cOuter = 2 * Math.PI * rOuter;
  const cInner = 2 * Math.PI * rInner;

  // Outer ring: segments expressed as fractions of BAC (= fraction of circumference).
  // The "savings" segment fills the visible gap between EAC and BAC when under budget.
  const outerSegs: Array<{ key: SliceKey; frac: number }> = [
    { key: "actuals", frac: bac > 0 ? aFill / bac : 0 },
    { key: "committed", frac: bac > 0 ? coFill / bac : 0 },
    { key: "expected", frac: bac > 0 ? expFill / bac : 0 },
    { key: "savings", frac: bac > 0 ? savings / bac : 0 },
  ];

  // Inner overspend arc — scaled against BAC, capped at full circle.
  const overspendFrac = bac > 0 ? Math.min(overspend / bac, 1) : 0;

  const activeSlices = hovered ? HOVER_TO_SLICES[hovered] : null;
  const isActive = (key: SliceKey) => activeSlices?.includes(key) ?? false;

  /* Per-slice values for the tooltip. Keyed on SliceKey only — aggregate
     hovers (ac/etc/eac/bac) don't show a tooltip because the row already
     displays the corresponding aggregate value. */
  const SLICE_VALUES: Record<SliceKey, number> = {
    actuals: a,
    committed: co,
    expected: exp,
    savings,
    overspend,
  };
  const SINGLE_SLICE_SET: ReadonlySet<HoverGroup> = new Set([
    "actuals", "committed", "expected", "savings", "overspend",
  ]);
  const tooltipSlice =
    hovered && SINGLE_SLICE_SET.has(hovered) ? (hovered as SliceKey) : null;

  /* Cursor-anchored tooltip position. Set by pointermove on arcs, cleared
     on pointerleave. Using Pointer events (not Mouse) so touch works too. */
  const containerRef = useRef<HTMLDivElement>(null);
  const [tipPos, setTipPos] = useState<{ x: number; y: number } | null>(null);
  const handlePointerMove = (e: React.PointerEvent) => {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;
    setTipPos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
  };
  const clearTip = () => setTipPos(null);

  let cursor = 0;
  return (
    <div ref={containerRef} className="relative shrink-0 touch-none" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label="Budget composition vs BAC">
        <g transform={`rotate(-90 ${cx} ${cy})`}>
          {/* Outer track — full BAC ring (hover sets BAC group, no tooltip) */}
          <circle
            cx={cx}
            cy={cy}
            r={rOuter}
            fill="none"
            className="ring-track cursor-pointer"
            strokeWidth={STROKE_OUTER}
            onPointerEnter={() => onHover("bac")}
            onPointerLeave={() => { onHover(null); clearTip(); }}
          />

          {/* Outer segments — Actuals → Committed → Expected → Savings */}
          {outerSegs.map((s) => {
            const start = cursor;
            cursor = start + s.frac;
            const len = s.frac * cOuter;
            if (len <= 0.001) return null;
            const active = isActive(s.key);
            return (
              <circle
                key={s.key}
                cx={cx}
                cy={cy}
                r={rOuter}
                fill="none"
                stroke={SLICE_COLORS[s.key]}
                strokeWidth={active ? STROKE_OUTER + 5 : STROKE_OUTER}
                strokeLinecap="butt"
                strokeDasharray={`${len} ${cOuter - len}`}
                strokeDashoffset={-start * cOuter}
                onPointerEnter={() => onHover(s.key)}
                onPointerLeave={() => { onHover(null); clearTip(); }}
                onPointerMove={handlePointerMove}
                className="cursor-pointer transition-[stroke-width] duration-200 ease-out"
              />
            );
          })}

          {/* Inner ring — only rendered when overspend > 0 */}
          {isOverspend && (
            <>
              <circle cx={cx} cy={cy} r={rInner} fill="none" className="ring-track" strokeWidth={STROKE_INNER} />
              <circle
                cx={cx}
                cy={cy}
                r={rInner}
                fill="none"
                stroke={SLICE_COLORS.overspend}
                strokeWidth={isActive("overspend") ? STROKE_INNER + 5 : STROKE_INNER}
                strokeLinecap="butt"
                strokeDasharray={`${overspendFrac * cInner} ${cInner - overspendFrac * cInner}`}
                onPointerEnter={() => onHover("overspend")}
                onPointerLeave={() => { onHover(null); clearTip(); }}
                onPointerMove={handlePointerMove}
                className="cursor-pointer transition-[stroke-width] duration-200 ease-out"
              />
            </>
          )}
        </g>
      </svg>

      {/* Center label */}
      <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
        <span className="text-[9px] uppercase tracking-wider text-muted-foreground">EAC</span>
        <span className={cn(
          "text-2xl font-bold font-mono tabular-nums leading-none mt-0.5",
          isOverspend ? "text-danger" : "text-etex-charcoal dark:text-gray-100",
        )}>
          {eacPct.toFixed(0)}%
        </span>
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground mt-1">
          of BAC
        </span>
      </div>

      {/* Tooltip — matches the rest of the app's popover style (InfoHint).
          Renders outside the wheel bounds via CSS transforms; quadrant-aware
          placement keeps it on-screen without complex clamping math. */}
      {tooltipSlice && tipPos && (() => {
        const value = SLICE_VALUES[tooltipSlice];
        const right = tipPos.x > size / 2;
        const bottom = tipPos.y > size / 2;
        const transform = `translate(${right ? "calc(-100% - 14px)" : "14px"}, ${bottom ? "calc(-100% - 14px)" : "14px"})`;
        return (
          <div
            className="absolute z-30 pointer-events-none rounded-lg bg-white shadow-lg shadow-black/10 ring-1 ring-gray-200 px-3 py-2 whitespace-nowrap animate-in fade-in-0 zoom-in-95 duration-150"
            style={{ left: tipPos.x, top: tipPos.y, transform }}
          >
            <div className="text-[11px] font-semibold text-gray-900 flex items-center gap-1.5">
              <span
                className="inline-block w-2 h-2 rounded-sm shrink-0"
                style={{ backgroundColor: SLICE_COLORS[tooltipSlice] }}
                aria-hidden
              />
              {SLICE_LABELS[tooltipSlice]}
            </div>
            <div className="font-mono tabular-nums text-[12px] text-gray-700 mt-1 pl-3.5">
              {formatAmount(value, 1)}
              <span className="ml-0.5 text-[10px] text-gray-400 font-semibold tracking-wide">k€</span>
              <span className="text-gray-300 mx-2">·</span>
              <span className="text-gray-500">{pctOfBac(value, bac).toFixed(0)}% of BAC</span>
            </div>
          </div>
        );
      })()}
    </div>
  );
}

/**
 * Stacked color dots that visually link a Summary row to its matching donut
 * arc(s). One dot per slice — A+C shows two, EAC three, BAC all four.
 * Scales up when the row's hover group is active.
 */
function SliceChip({ slices, active }: { slices: SliceKey[]; active: boolean }) {
  return (
    <span className="inline-flex items-center gap-0.5 mr-2 align-middle">
      {slices.map((s) => (
        <span
          key={s}
          className={cn(
            "w-2.5 h-2.5 rounded-sm shrink-0 transition-transform duration-150 inline-block",
            active && "scale-125",
          )}
          style={{ backgroundColor: SLICE_COLORS[s] }}
          aria-hidden
        />
      ))}
    </span>
  );
}

/**
 * Wraps a row so hovering it activates its `hoverGroup` — which the chart maps
 * to one or more arcs. Rows without a meaningful group can omit it.
 */
function RowHover({
  hoverGroup,
  hovered,
  onHover,
  children,
  className,
}: {
  hoverGroup?: HoverGroup | null;
  hovered: HoverGroup | null;
  onHover: (k: HoverGroup | null) => void;
  children: React.ReactNode;
  className?: string;
}) {
  const active = hoverGroup != null && hovered === hoverGroup;
  return (
    <div
      onMouseEnter={hoverGroup ? () => onHover(hoverGroup) : undefined}
      onMouseLeave={hoverGroup ? () => onHover(null) : undefined}
      className={cn(
        "transition-colors duration-150",
        hoverGroup && "cursor-pointer",
        active && "bg-muted/60",
        className,
      )}
    >
      {children}
    </div>
  );
}

/* ── Contingency bar ──────────────────────────────────────────── */

function ContingencyBar({ budgeted, consumed }: { budgeted: number; consumed: number }) {
  const pct = budgeted > 0 ? Math.min((consumed / budgeted) * 100, 100) : 0;

  return (
    <div className="mt-2">
      <div className="h-1.5 rounded-full bg-secondary overflow-hidden">
        <div
          className={cn(
            "h-full rounded-full transition-all duration-500",
            pct >= 100 ? "bg-danger" : pct > 75 ? "bg-warning" : "bg-etex-orange",
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="flex justify-between mt-0.5">
        <span className="text-[10px] text-muted-foreground">{pct.toFixed(0)}% used</span>
        <span className="text-[10px] text-muted-foreground">
          {formatCurrency(budgeted - consumed)} remaining
        </span>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   BudgetTab
   ═══════════════════════════════════════════════════════════════════ */

interface BudgetTabProps {
  projectId: string;
  budget: Budget | null;
  /** VAC from the most recent snapshot (previous month) */
  prevMonthVAC?: number | null;
  /** Period label of the snapshot used for M-1 (e.g. "2026-03") */
  prevMonthLabel?: string | null;
}

export function BudgetTab({ projectId, budget: propBudget, prevMonthVAC, prevMonthLabel }: BudgetTabProps) {
  const { record: budget, patch } = useOptimisticRecord<Budget & Record<string, unknown>>({
    initial: propBudget as (Budget & Record<string, unknown>) | null,
    url: `/api/projects/${projectId}/budget`,
  });
  const [hovered, setHovered] = useState<HoverGroup | null>(null);

  if (!budget) {
    return <div className="text-sm text-muted-foreground py-6">No budget data available.</div>;
  }

  /* ── Computed values (centralized in lib/calculations) ───────── */
  const actualsCommitted = calcActualsCommitted(budget);
  const etc = calcETC(budget);
  const eac = calcEAC(budget);
  const variance = calcVariance(budget);
  const variancePct = calcVariancePct(budget);
  const overspend = calcOverspend(budget);
  const riskContRemaining = budget.riskContingencyBudgeted - budget.riskContingencyConsumed;
  const mgmtContRemaining = budget.mgmtContingencyBudgeted - budget.mgmtContingencyConsumed;

  /* Editable inputs — the only fields the user types directly.
     Each input's group is also its slice key (single-arc highlight). */
  const inputs: Array<{ label: string; field: "actuals" | "committed" | "expected"; value: number; hint: string; group: HoverGroup }> = [
    { label: "Actuals", field: "actuals", value: budget.actuals, hint: "Current project spend to date", group: "actuals" },
    { label: "Committed", field: "committed", value: budget.committed, hint: "Existing purchase order commitments", group: "committed" },
    { label: "Expected", field: "expected", value: budget.expected, hint: "Forecast spend not yet committed", group: "expected" },
  ];

  /* VAC ties to either the savings arc (under budget) or the overrun ring (over budget). */
  const vacGroup: HoverGroup | null =
    variance > 0.05 ? "savings"
      : variance < -0.05 ? "overspend"
        : null;
  const vacSublabel =
    variance > 0.05 ? "Savings — under budget"
      : variance < -0.05 ? "Overrun — over budget"
        : "On budget";

  return (
    <div className="space-y-6">

      {/* ── Inputs (full width) — chips tie each row to its wheel segment ─── */}
      <div className="rounded-md border border-border bg-card">
        <div className="px-4 py-2 border-b border-border text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
          Inputs
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 divide-y sm:divide-y-0 sm:divide-x divide-border">
          {inputs.map((row) => (
            <RowHover key={row.field} hoverGroup={row.group} hovered={hovered} onHover={setHovered}>
              <div className="grid grid-cols-[1fr_140px] items-center gap-3 px-3 py-2">
                <RowLabel hint={row.hint}>
                  <SliceChip slices={HOVER_TO_SLICES[row.group]} active={hovered === row.group} />
                  {row.label}
                </RowLabel>
                <AutoAmount value={row.value} onSave={(v) => patch(row.field, v)} />
              </div>
            </RowHover>
          ))}
        </div>
      </div>

      {/* ── Summary card: rows on the left, donut on the right (same card) ─── */}
      <div className="rounded-md border border-border bg-card">
        <div className="px-4 py-2 border-b border-border text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
          Summary
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_auto] items-center gap-4 lg:gap-6 p-2 lg:pr-6">
          {/* Rows */}
          <div className="min-w-0">
            {/* BAC — hover lights up the entire outer ring */}
            <RowHover hoverGroup="bac" hovered={hovered} onHover={setHovered}>
              <div className="budget-row computed-row grid grid-cols-[1fr_180px] items-center gap-3 py-1.5 px-3">
                <RowLabel hint="Sum of CAPEX + OPEX from the Budget Breakdown above.">
                  <SliceChip slices={HOVER_TO_SLICES.bac} active={hovered === "bac"} />
                  BAC
                </RowLabel>
                <ComputedAmount value={budget.bac} />
              </div>
            </RowHover>

            {/* Actuals + Committed */}
            <RowHover hoverGroup="ac" hovered={hovered} onHover={setHovered}>
              <div className="budget-row computed-row grid grid-cols-[1fr_180px] items-center gap-3 py-1.5 px-3">
                <div className="min-w-0">
                  <RowLabel hint="Spent + locked-in commitments.">
                    <SliceChip slices={HOVER_TO_SLICES.ac} active={hovered === "ac"} />
                    Actuals + Committed
                  </RowLabel>
                  <div className="text-[10px] text-muted-foreground">
                    {pctOfBac(actualsCommitted, budget.bac).toFixed(0)}% of BAC
                  </div>
                </div>
                <ComputedAmount value={actualsCommitted} />
              </div>
            </RowHover>

            {/* ETC */}
            <RowHover hoverGroup="etc" hovered={hovered} onHover={setHovered}>
              <div className="budget-row computed-row grid grid-cols-[1fr_180px] items-center gap-3 py-1.5 px-3">
                <div className="min-w-0">
                  <RowLabel hint="Remaining cost still to be incurred.">
                    <SliceChip slices={HOVER_TO_SLICES.etc} active={hovered === "etc"} />
                    ETC
                  </RowLabel>
                  <div className="text-[10px] text-muted-foreground">Committed + Expected</div>
                </div>
                <ComputedAmount value={etc} />
              </div>
            </RowHover>

            {/* EAC */}
            <RowHover hoverGroup="eac" hovered={hovered} onHover={setHovered}>
              <div className="budget-row computed-row grid grid-cols-[1fr_180px] items-center gap-3 py-1.5 px-3">
                <div className="min-w-0">
                  <RowLabel hint="Forecast total spend by project end.">
                    <SliceChip slices={HOVER_TO_SLICES.eac} active={hovered === "eac"} />
                    EAC
                  </RowLabel>
                  <div className="text-[10px] text-muted-foreground">Actuals + Committed + Expected</div>
                </div>
                <ComputedAmount value={eac} sentiment={overspend > 0 ? "negative" : undefined} />
              </div>
            </RowHover>

            {/* VAC — chip ties to savings or overrun slice (when non-zero) */}
            <RowHover hoverGroup={vacGroup} hovered={hovered} onHover={setHovered}>
              <div className="budget-row computed-row grid grid-cols-[1fr_180px] items-center gap-3 py-1.5 px-3">
                <div className="min-w-0">
                  <RowLabel hint="Variance at Completion = BAC − EAC. Positive = savings; negative = overrun.">
                    {vacGroup && <SliceChip slices={HOVER_TO_SLICES[vacGroup]} active={hovered === vacGroup} />}
                    VAC
                    <span className="ml-1.5 text-[10px] text-muted-foreground">
                      {formatVariance(variancePct, { suffix: "%" }).display}
                    </span>
                  </RowLabel>
                  <div className="text-[10px] text-muted-foreground truncate">{vacSublabel}</div>
                </div>
                <div>
                  <ComputedAmount value={variance} variance />
                  {prevMonthVAC != null && (() => {
                    const prev = formatVariance(prevMonthVAC, { suffix: "" });
                    const color =
                      prev.sentiment === "positive" ? "text-success"
                        : prev.sentiment === "negative" ? "text-danger" : "text-muted-foreground";
                    const delta = variance - prevMonthVAC;
                    const showArrow = Math.abs(delta) >= 0.05;
                    const improving = delta > 0;
                    return (
                      <div className="flex items-center justify-end gap-1.5 px-2.5 -mt-1">
                        <span className="text-[10px] text-muted-foreground">
                          prev{prevMonthLabel ? ` (${prevMonthLabel})` : ""}:
                        </span>
                        <span className={cn("text-[10px] font-mono font-medium tabular-nums", color)}>
                          {prev.display}
                        </span>
                        <span className="text-[9px] text-muted-foreground">k€</span>
                        {showArrow && (
                          <span className={cn("text-[10px] font-semibold", improving ? "text-success" : "text-danger")}>
                            {improving ? "↑" : "↓"}
                          </span>
                        )}
                      </div>
                    );
                  })()}
                </div>
              </div>
            </RowHover>
          </div>

          {/* Donut — embedded in the same card so the rows above are its legend */}
          <div className="flex justify-center lg:justify-end p-2">
            <BudgetWheel
              actuals={budget.actuals}
              committed={budget.committed}
              expected={budget.expected}
              eac={eac}
              bac={budget.bac}
              hovered={hovered}
              onHover={setHovered}
            />
          </div>
        </div>
      </div>

      {/* ── Contingencies ─────────────────────────────────────── */}
      <div>
        <div className="grid grid-cols-1 sm:grid-cols-2">
          {([
            {
              title: "Risk contingency",
              titleHint: "Reserve set aside to cover identified risk events (included in BAC)",
              budgetedField: "riskContingencyBudgeted" as const,
              consumedField: "riskContingencyConsumed" as const,
              budgeted: budget.riskContingencyBudgeted,
              consumed: budget.riskContingencyConsumed,
              remaining: riskContRemaining,
            },
            {
              title: "Management contingency",
              titleHint: "Management reserve for unforeseen scope or cost changes (included in BAC)",
              budgetedField: "mgmtContingencyBudgeted" as const,
              consumedField: "mgmtContingencyConsumed" as const,
              budgeted: budget.mgmtContingencyBudgeted,
              consumed: budget.mgmtContingencyConsumed,
              remaining: mgmtContRemaining,
            },
          ]).map((cont) => (
            <div key={cont.title} className="px-4 py-3">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-2 flex items-center gap-1">
                {cont.title}
                <InfoHint label={cont.title} text={cont.titleHint} />
              </div>
              <div className="">
                <div className="grid grid-cols-[1fr_160px] items-center gap-3 py-1">
                  <RowLabel hint="Total amount allocated for this contingency">Budgeted</RowLabel>
                  <AutoAmount value={cont.budgeted} onSave={(v) => patch(cont.budgetedField, v)} />
                </div>
                <div className="grid grid-cols-[1fr_160px] items-center gap-3 py-1">
                  <RowLabel hint="Portion of the contingency already utilised">Consumed</RowLabel>
                  <AutoAmount value={cont.consumed} onSave={(v) => patch(cont.consumedField, v)} />
                </div>
                <div className="grid grid-cols-[1fr_160px] items-center gap-3 py-1 computed-row -mx-4 px-4">
                  <RowLabel hint="Budgeted minus consumed — available contingency buffer">Remaining</RowLabel>
                  <ComputedAmount value={cont.remaining} sentiment={cont.remaining < 0 ? "negative" : "neutral"} />
                </div>
              </div>
              <ContingencyBar budgeted={cont.budgeted} consumed={cont.consumed} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
