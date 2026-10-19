"use client";

import { useState, useEffect, useMemo, useRef } from "react";
import { Plus, Trash2 } from "lucide-react";
import { cn, formatAmount, formatCurrency, formatDate, roundTo } from "@/lib/utils";
import { AutoInput, AutoGrowInput, AutoDateInput, AutoMetric } from "@/components/ui/auto-fields";
import { InfoHint } from "@/components/ui/info-hint";
import { useOptimisticList } from "@/hooks/use-optimistic-list";
import { useReadOnly } from "@/components/ui/read-only-context";
import { DataGrid, type DataGridColumn } from "@/components/ui/data-grid";
import { computeRiskMetrics } from "@/lib/risk-calculations";
import type { Risk } from "@/lib/db/models";
import type { RiskSummary } from "@/lib/risk-summary";

/* ── Constants ─────────────────────────────────────────────────── */

const IMPACT_ORDER: Record<string, number> = {
  VERY_HIGH: 0, HIGH: 1, MODERATE: 2, LOW: 3,
};

const IMPACTS = ["VERY_HIGH", "HIGH", "MODERATE", "LOW"] as const;

export const IMPACT_STYLE: Record<string, { dot: string; text: string; bg: string; fg: string }> = {
  ISSUE:     { dot: "bg-red-900",   text: "text-red-700",   bg: "bg-red-900",       fg: "text-white" },
  VERY_HIGH: { dot: "bg-red-700",   text: "text-red-700",   bg: "bg-red-200",       fg: "text-red-900" },
  HIGH:      { dot: "bg-red-500",   text: "text-red-600",   bg: "bg-red-100",       fg: "text-red-800" },
  MODERATE:  { dot: "bg-amber-400", text: "text-amber-600", bg: "bg-yellow-100",    fg: "text-yellow-800" },
  LOW:       { dot: "bg-green-500", text: "text-green-600", bg: "bg-green-100",     fg: "text-green-800" },
};

export const IMPACT_LABEL: Record<string, string> = {
  VERY_HIGH: "Very High", HIGH: "High", MODERATE: "Moderate", LOW: "Low",
};

/* ── Impact cell — fills full cell, acts as selector ─────────── */

function ImpactCell({ value, onSave }: { value: string; onSave?: (v: string) => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const interactive = !!onSave;

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const style = IMPACT_STYLE[value] ?? IMPACT_STYLE.MODERATE;

  return (
    <div ref={ref} className="relative -mx-1 -my-0.5">
      <div
        onClick={interactive ? () => setOpen(!open) : undefined}
        className={cn(
          "flex items-center justify-center px-2 py-1.5 rounded-sm text-[10px] font-bold uppercase tracking-wide transition-colors",
          style.bg, style.fg,
          interactive && "cursor-pointer hover:opacity-90",
        )}
      >
        {IMPACT_LABEL[value] ?? value}
      </div>
      {open && interactive && (
        <div className="absolute z-20 top-full mt-1 left-0 dropdown-surface rounded py-1 min-w-28">
          {IMPACTS.map((imp) => {
            const s = IMPACT_STYLE[imp];
            return (
              <button
                key={imp}
                onClick={() => { onSave!(imp); setOpen(false); }}
                className={cn(
                  "w-full text-left px-3 py-1.5 text-xs hover:bg-muted flex items-center gap-2 transition-colors",
                  imp === value && "font-semibold",
                )}
              >
                <span className={cn("w-2 h-2 rounded-full shrink-0", s.dot)} />
                {IMPACT_LABEL[imp]}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

/* ── Inline number input (for risk row fields) ───────────────── */

function AutoNumber({
  value, onSave, placeholder = "—", suffix, decimals = 0,
}: {
  value: number | null | undefined;
  onSave: (v: number | null) => void;
  placeholder?: string;
  suffix?: string;
  decimals?: number;
}) {
  const [draft, setDraft] = useState(value != null ? String(roundTo(value, decimals)) : "");
  const [editing, setEditing] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!editing) setDraft(value != null ? String(roundTo(value, decimals)) : "");
  }, [value, editing, decimals]);

  const commit = (raw: string) => {
    const trimmed = raw.trim();
    if (trimmed === "") { if (value != null) onSave(null); }
    else { const n = roundTo(parseFloat(trimmed), decimals); if (!isNaN(n) && n !== value) onSave(n); }
    setEditing(false);
  };

  return (
    <div className="relative">
      <input
        ref={inputRef}
        type={editing ? "number" : "text"}
        inputMode="numeric"
        value={editing ? draft : (value != null ? formatAmount(value, decimals) : "")}
        placeholder={placeholder}
        onChange={(e) => setDraft(e.target.value)}
        onFocus={() => { setEditing(true); setDraft(value != null ? String(roundTo(value, decimals)) : ""); setTimeout(() => inputRef.current?.select(), 0); }}
        onBlur={() => commit(draft)}
        onKeyDown={(e) => {
          if (e.key === "Enter") { commit(draft); inputRef.current?.blur(); }
          if (e.key === "Escape") setEditing(false);
        }}
        className={cn("form-control w-full text-right font-mono text-xs tabular-nums px-1.5", suffix && "pr-7")}
        style={editing ? { MozAppearance: "textfield" } as React.CSSProperties : undefined}
      />
      {suffix && (
        <span className="absolute top-1/2 -translate-y-1/2 right-1.5 text-[9px] text-gray-400 pointer-events-none font-semibold">
          {suffix}
        </span>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   RisksTab
   ═══════════════════════════════════════════════════════════════════ */

/**
 * Editable risk-summary inputs stored on the Project. Decoupled from the
 * Risk table — RIAC import autofills these and the user can edit them.
 */
export interface RiskCountInputs {
  risksIssuesCount: number | null;
  risksHighCount: number | null;
  risksModerateCount: number | null;
  risksLowCount: number | null;
  risksIdentifiedCount: number | null;
  risksQuantifiedCount: number | null;
  totalCostAtRisk: number | null;
  totalTimeImpact: number | null;
}

interface RisksTabProps {
  projectId: string;
  risks: Risk[];
  riskSummary: RiskSummary;
  riskCounts: RiskCountInputs;
  eac: number;
  /** Effective project start (actualStartDate ?? createdAt). Used to anchor time-at-risk %. */
  projectStart: Date | string | null;
  plannedCompletionDate: Date | string | null;
  onPatchProject: (fields: Record<string, unknown>) => void;
  toolbar?: React.ReactNode;
}

export function RisksTab({ projectId, risks: propRisks, riskSummary, riskCounts, eac, projectStart, plannedCompletionDate, onPatchProject, toolbar }: RisksTabProps) {
  const readOnly = useReadOnly();
  const baseUrl = `/api/projects/${projectId}/risks`;

  const createOptimistic = useMemo(
    () => () =>
      ({
        id: `_tmp_${Date.now()}`,
        projectId,
        riskNumber: null,
        type: "RISK",
        riskStatement: "",
        ifClause: null,
        dueToClause: null,
        thenClause: null,
        impact: "MODERATE",
        category: null,
        probability: null,
        costImpact: null,
        timeImpact: null,
        weight: null,
        counterMeasures: null,
        responseStrategy: null,
        ownerName: null,
        completionDate: null,
        status: "OPEN",
        comments: null,
        createdAt: new Date(),
        updatedAt: new Date(),
      }) as Risk,
    [projectId],
  );

  const createPayload = useMemo(
    () => () => ({ riskStatement: "", impact: "MODERATE" }),
    [],
  );

  const { items, add, patch, remove } = useOptimisticList<Risk>({
    initial: propRisks,
    baseUrl,
    createOptimistic,
    createPayload,
  });

  /* ── Sorted risks: Issues first, then by weight desc, then by impact ──
     Drives the single editable detail register (capped at top 5). */
  const sorted = useMemo(
    () =>
      [...items].sort((a, b) => {
        if (a.type === "ISSUE" && b.type !== "ISSUE") return -1;
        if (a.type !== "ISSUE" && b.type === "ISSUE") return 1;
        const w = (b.weight ?? 0) - (a.weight ?? 0);
        if (w !== 0) return w;
        return (IMPACT_ORDER[a.impact] ?? 5) - (IMPACT_ORDER[b.impact] ?? 5);
      }),
    [items],
  );

  /* ── Computed risk exposure metrics (centralized) ─────────── */

  const riskMetrics = useMemo(
    () => computeRiskMetrics(riskSummary, eac, projectStart, plannedCompletionDate),
    [riskSummary, eac, projectStart, plannedCompletionDate],
  );

  /* ── KPI summary — all editable inputs (autofilled by RIAC) ───── */

  /** Editable summary inputs — stored on Project, autofilled by RIAC. */
  const EDITABLE_COUNT_FIELDS: {
    field: keyof RiskCountInputs;
    label: string;
    dot?: string;
    color: string;
    unit: string;
    integer: boolean;
    hint: string;
  }[] = [
    { field: "risksIssuesCount",     label: "Issues",       dot: "bg-red-900",              color: "text-red-700",             unit: "",   integer: true,  hint: "Active problems requiring immediate action. Editable; autofilled by RIAC import." },
    { field: "risksHighCount",       label: "High",         dot: IMPACT_STYLE.HIGH.dot,     color: IMPACT_STYLE.HIGH.text,     unit: "",   integer: true,  hint: "High-impact risks. Editable; autofilled by RIAC import." },
    { field: "risksModerateCount",   label: "Moderate",     dot: IMPACT_STYLE.MODERATE.dot, color: IMPACT_STYLE.MODERATE.text, unit: "",   integer: true,  hint: "Moderate-impact risks. Editable; autofilled by RIAC import." },
    { field: "risksLowCount",        label: "Low",          dot: IMPACT_STYLE.LOW.dot,      color: IMPACT_STYLE.LOW.text,      unit: "",   integer: true,  hint: "Low-impact risks. Editable; autofilled by RIAC import." },
    { field: "totalCostAtRisk",      label: "Cost at Risk", color: "text-red-600",                                              unit: "k€", integer: false, hint: "Total potential financial exposure from open risks (k€). Editable; autofilled by RIAC import." },
    { field: "totalTimeImpact",      label: "Time Impact",  color: "text-red-600",                                              unit: "d",  integer: true,  hint: "Worst-case schedule impact in days. Editable; autofilled by RIAC import." },
  ];

  // Closed = Identified − (Issues + High + Moderate + Low)
  const closedCount =
    (riskCounts.risksIdentifiedCount ?? 0) -
    ((riskCounts.risksIssuesCount ?? 0) +
      (riskCounts.risksHighCount ?? 0) +
      (riskCounts.risksModerateCount ?? 0) +
      (riskCounts.risksLowCount ?? 0));

  // Risk Level % (probability-weighted EMV/EAC) was dropped: it required
  // iterating the full risk register which no longer exists — the detail
  // table only holds the top 5. Cost at Risk % remains as the unweighted
  // worst-case dimension, sourced from project.totalCostAtRisk.
  const EXPOSURE_FIELDS: {
    key: keyof typeof riskMetrics;
    label: string;
    suffix: string;
    color: string;
    hint: string;
  }[] = [
    { key: "costAtRiskPct", label: "Cost at Risk", suffix: "%",  color: "text-red-600",   hint: "Worst-case cost exposure as % of EAC (unweighted)" },
    { key: "timeAtRiskPct", label: "Time at Risk", suffix: "%",  color: "text-amber-600", hint: "Max time impact as % of planned project duration, measured from actual start date" },
  ];

  /* ── RiskGrid columns (editable) ───────────────────────────── */

  const columns: DataGridColumn<Risk>[] = useMemo(() => [
    {
      id: "riskStatement",
      header: "Risk Statement",
      hint: "Describe the risk event — what could happen and its impact",
      width: "minmax(0,2.5fr)",
      render: (r) => (
        <span className="text-foreground whitespace-pre-wrap wrap-break-word">{r.riskStatement || <span className="text-muted-foreground">—</span>}</span>
      ),
      renderEdit: (r) => (
        <AutoGrowInput
          value={r.riskStatement}
          onSave={(v) => patch(r.id, "riskStatement", v)}
          placeholder="Describe the risk…"
        />
      ),
    },
    {
      id: "impact",
      header: "Impact",
      hint: "Impact level: Issue (active problem), High, Moderate, Low, or Closed",
      width: "80px",
      align: "center",
      render: (r) => <ImpactCell value={r.impact} />,
      renderEdit: (r) => <ImpactCell value={r.impact} onSave={(v) => patch(r.id, "impact", v)} />,
    },
    {
      id: "probability",
      header: "Prob.",
      hint: "Likelihood of this risk occurring, as a percentage",
      width: "72px",
      align: "right",
      render: (r) => (
        <span className="font-mono text-muted-foreground tabular-nums text-sm">
          {r.probability != null ? `${r.probability}%` : "—"}
        </span>
      ),
      renderEdit: (r) => <AutoNumber value={r.probability} onSave={(v) => patch(r.id, "probability", v)} suffix="%" />,
    },
    {
      id: "costImpact",
      header: "Cost",
      hint: "Potential financial impact if the risk materialises (k€)",
      width: "88px",
      align: "right",
      render: (r) => (
        <span className="font-mono text-muted-foreground tabular-nums text-sm">
          {r.costImpact != null ? formatAmount(r.costImpact, 1) : "—"}
        </span>
      ),
      renderEdit: (r) => <AutoNumber value={r.costImpact} onSave={(v) => patch(r.id, "costImpact", v)} suffix="k€" decimals={1} />,
    },
    {
      id: "timeImpact",
      header: "Time",
      hint: "Potential schedule impact in days if the risk materialises",
      width: "68px",
      align: "right",
      render: (r) => (
        <span className="font-mono text-muted-foreground tabular-nums text-sm">
          {r.timeImpact != null ? `${r.timeImpact}d` : "—"}
        </span>
      ),
      renderEdit: (r) => <AutoNumber value={r.timeImpact} onSave={(v) => patch(r.id, "timeImpact", v)} suffix="d" />,
    },
    {
      id: "counterMeasures",
      header: "Counter Measures",
      hint: "Actions planned or underway to mitigate this risk",
      width: "minmax(0,1.5fr)",
      render: (r) => (
        <span className="text-foreground whitespace-pre-wrap wrap-break-word">{r.counterMeasures || <span className="text-muted-foreground">—</span>}</span>
      ),
      renderEdit: (r) => (
        <AutoGrowInput
          value={r.counterMeasures ?? ""}
          onSave={(v) => patch(r.id, "counterMeasures", v || null)}
          placeholder="—"
        />
      ),
    },
    {
      id: "ownerName",
      header: "Owner",
      hint: "Person responsible for monitoring and managing this risk",
      width: "90px",
      render: (r) => <span className="text-foreground wrap-break-word">{r.ownerName || <span className="text-muted-foreground">—</span>}</span>,
      renderEdit: (r) => (
        <AutoInput
          value={r.ownerName ?? ""}
          onSave={(v) => patch(r.id, "ownerName", v || null)}
          placeholder="—"
        />
      ),
    },
    {
      id: "completionDate",
      header: "Due Date",
      hint: "Target date for counter-measure completion",
      width: "100px",
      render: (r) => {
        if (!r.completionDate) return <span className="text-muted-foreground">—</span>;
        return (
          <span className="font-mono text-muted-foreground text-sm">
            {formatDate(r.completionDate)}
          </span>
        );
      },
      renderEdit: (r) => <AutoDateInput value={r.completionDate} onSave={(v) => patch(r.id, "completionDate", v || null)} />,
    },
    {
      id: "actions",
      header: "",
      width: "28px",
      render: () => null,
      renderEdit: (r) => (
        <button
          onClick={() => remove(r.id)}
          className="opacity-0 group-hover:opacity-100 text-gray-400 hover:text-red-500 transition-all p-1 rounded"
        >
          <Trash2 size={13} />
        </button>
      ),
    },
  ], [patch, remove]);

  return (
    <div className="space-y-4">

      {/* ═══ Risk Summary — editable inputs, autofilled by RIAC ════════ */}
      <div>
        <div className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground mb-2">Risk Summary</div>
        <div className="summary-grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6">
          {EDITABLE_COUNT_FIELDS.map((f) => (
            <div key={f.field} className="summary-cell">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1 flex items-center gap-0.5">
                {f.dot && <span className={cn("w-2 h-2 rounded-full shrink-0 inline-block mr-1", f.dot)} />}
                {f.label}
                <InfoHint label={f.label} text={f.hint} />
              </div>
              <div className={cn("text-xl font-bold leading-tight", f.color)}>
                <AutoMetric
                  value={riskCounts[f.field]}
                  onSave={(v) => onPatchProject({ [f.field]: v })}
                  unit={f.unit}
                  integer={f.integer}
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ═══ Exposure ════════════════════════════════════════════════ */}
      <div>
        <div className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground mb-2">Exposure</div>
        <div className="summary-grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6">
          {/* Identified — editable count */}
          <div className="summary-cell">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1 flex items-center gap-0.5">
              Identified
              <InfoHint label="Identified" text="Total number of risks identified. Editable; autofilled by RIAC import." />
            </div>
            <div className="text-xl font-bold leading-tight text-etex-charcoal dark:text-gray-100">
              <AutoMetric
                value={riskCounts.risksIdentifiedCount}
                onSave={(v) => onPatchProject({ risksIdentifiedCount: v })}
                unit=""
                integer
              />
            </div>
          </div>

          {/* Quantified — editable count */}
          <div className="summary-cell">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1 flex items-center gap-0.5">
              Quantified
              <InfoHint label="Quantified" text="Risks with probability and impact assigned. Editable; autofilled by RIAC import." />
            </div>
            <div className="text-xl font-bold leading-tight text-etex-charcoal dark:text-gray-100">
              <AutoMetric
                value={riskCounts.risksQuantifiedCount}
                onSave={(v) => onPatchProject({ risksQuantifiedCount: v })}
                unit=""
                integer
              />
            </div>
          </div>

          {/* Closed — computed: Identified − (Issues + High + Moderate + Low) */}
          <div className="summary-cell">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1 flex items-center gap-0.5">
              Closed
              <InfoHint label="Closed" text="Auto-calculated: Identified − (Issues + High + Moderate + Low)" />
            </div>
            <div className="text-xl font-bold font-mono tabular-nums leading-tight py-0.5 text-etex-charcoal dark:text-gray-100">
              {closedCount}
            </div>
          </div>

          {/* Derived exposure metrics */}
          {EXPOSURE_FIELDS.map((f) => {
            const val = riskMetrics[f.key];
            return (
              <div key={f.key + f.suffix} className="summary-cell">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1 flex items-center gap-0.5">
                  {f.label}
                  <InfoHint label={f.label} text={f.hint} />
                </div>
                <div className="flex items-baseline gap-1">
                  <span className={cn(
                    "text-xl font-bold font-mono tabular-nums leading-tight py-0.5",
                    val > 0 ? f.color : "text-etex-charcoal dark:text-gray-100",
                  )}>
                    {f.suffix === "k€" ? formatCurrency(val, { decimals: 1, suffix: "" }) : `${val}`}
                  </span>
                  <span className="text-[11px] font-semibold text-muted-foreground shrink-0">{f.suffix}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ═══ Top 5 Risks & Issues — the editable detail register ═══════ */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1">
            Risks & Issues
            <InfoHint
              label="Risks & Issues"
              text="The detailed risk and issue register. Aggregate counts above (Issues / High / Moderate / Low / Cost at Risk / Time Impact) cover the full risk register and are entered manually or autofilled by RIAC import."
              className="ml-1"
            />
          </span>
          {toolbar}
        </div>

        <DataGrid
          columns={columns}
          data={sorted}
          editable={!readOnly}
          rowKey={(r) => r.id}
          minWidth={780}
          footer={
            !readOnly ? (
              <button
                onClick={add}
                className="flex items-center gap-1.5 w-full px-4 py-2.5 text-[12px] text-muted-foreground
                           hover:text-etex-orange hover:bg-etex-orange-50 transition-colors"
              >
                <Plus size={13} />
                Add risk<span className="text-gray-300 ml-1">({items.length})</span>
              </button>
            ) : undefined
          }
        />
      </div>
    </div>
  );
}
