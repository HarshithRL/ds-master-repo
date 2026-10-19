"use client";

import { useMemo, useRef, useState, useEffect, memo } from "react";
import { Plus, Trash2 } from "lucide-react";
import { cn, formatDate } from "@/lib/utils";
import { AutoGrowInput, AutoDateInput, AutoMetric } from "@/components/ui/auto-fields";
import { DataGrid, type DataGridColumn } from "@/components/ui/data-grid";
import { useOptimisticList } from "@/hooks/use-optimistic-list";
import { useReadOnly } from "@/components/ui/read-only-context";
import { SCOPE_CHANGE_STATUSES } from "@/lib/constants";
import type { ScopeChange } from "@/lib/db/models";

/* ── Status Cell (dropdown badge) ─────────────────────────────────── */

const StatusCell = memo(function StatusCell({
  value,
  onSave,
}: {
  value: string;
  onSave: (v: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const status = SCOPE_CHANGE_STATUSES.find((s) => s.key === value) ?? SCOPE_CHANGE_STATUSES[0];

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={cn(
          "inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium transition-colors cursor-pointer",
          status.bgColor, status.textColor, status.darkBg, status.darkText,
        )}
      >
        {status.label}
      </button>
      {open && (
        <div className="absolute z-30 top-full left-0 mt-1 dropdown-surface rounded py-1 min-w-30">
          {SCOPE_CHANGE_STATUSES.map((s) => (
            <button
              key={s.key}
              type="button"
              onClick={() => { onSave(s.key); setOpen(false); }}
              className={cn(
                "w-full text-left px-3 py-1.5 text-xs hover:bg-muted transition-colors",
                s.key === value && "font-semibold",
              )}
            >
              <span className={cn("inline-block w-2 h-2 rounded-full mr-2", s.bgColor)} />
              {s.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
});

/* ═══════════════════════════════════════════════════════════════════
   ScopeChangesTab
   ═══════════════════════════════════════════════════════════════════ */

const MAX_SCOPE_CHANGES = 50;

interface ScopeChangesTabProps {
  projectId: string;
  scopeChanges: ScopeChange[];
  toolbar?: React.ReactNode;
}

export function ScopeChangesTab({ projectId, scopeChanges: propScopeChanges, toolbar }: ScopeChangesTabProps) {
  const readOnly = useReadOnly();
  const baseUrl = `/api/projects/${projectId}/scope-changes`;

  const createOptimistic = useMemo(
    () => () =>
      ({
        id: `_tmp_${Date.now()}`,
        projectId,
        submittedDate: null,
        description: "",
        impactCost: null,
        impactSchedule: null,
        impactCostValue: null,
        impactScheduleValue: null,
        status: "OPEN",
        createdAt: new Date(),
        updatedAt: new Date(),
      }) as ScopeChange,
    [projectId],
  );

  const createPayload = useMemo(
    () => () => ({ description: "", status: "OPEN" }),
    [],
  );

  const { items, add, patch, remove } = useOptimisticList<ScopeChange>({
    initial: propScopeChanges,
    baseUrl,
    createOptimistic,
    createPayload,
  });

  const canAdd = items.length < MAX_SCOPE_CHANGES;

  const columns: DataGridColumn<ScopeChange>[] = useMemo(() => [
    {
      id: "submittedDate",
      header: "Date Submitted",
      hint: "Date the scope change was submitted",
      width: "120px",
      renderEdit: (sc) => (
        <AutoDateInput value={sc.submittedDate} onSave={(v) => patch(sc.id, "submittedDate", v)} />
      ),
      render: (sc) => <span className="text-foreground font-mono text-xs tabular-nums">{sc.submittedDate ? formatDate(sc.submittedDate) : <span className="text-muted-foreground">—</span>}</span>,
    },
    {
      id: "description",
      header: "Scope Change",
      hint: "Description of the scope change request",
      width: "minmax(0,2fr)",
      renderEdit: (sc) => (
        <AutoGrowInput value={sc.description} onSave={(v) => patch(sc.id, "description", v)} placeholder="Describe the scope change…" maxRows={5} />
      ),
      render: (sc) => <span className="text-foreground">{sc.description || <span className="text-muted-foreground">—</span>}</span>,
    },
    {
      id: "impactCostValue",
      header: "Impact Cost",
      hint: "Numeric cost impact in k€. Used for one-pager totals (Eval / Approved).",
      width: "130px",
      align: "right" as const,
      renderEdit: (sc) => (
        <div className="space-y-0.5">
          <AutoMetric
            value={sc.impactCostValue}
            onSave={(v) => patch(sc.id, "impactCostValue", v)}
            unit="k€"
          />
          {sc.impactCost && (
            <div
              className="text-[10px] text-muted-foreground/80 italic truncate"
              title={`Legacy note: ${sc.impactCost}`}
            >
              {sc.impactCost}
            </div>
          )}
        </div>
      ),
      render: (sc) => (
        <div className="text-right">
          <span className="font-mono tabular-nums text-foreground">
            {sc.impactCostValue != null ? `${sc.impactCostValue} k€` : <span className="text-muted-foreground">—</span>}
          </span>
          {sc.impactCost && <div className="text-[10px] text-muted-foreground/80 italic truncate" title={sc.impactCost}>{sc.impactCost}</div>}
        </div>
      ),
    },
    {
      id: "impactScheduleValue",
      header: "Impact Schedule",
      hint: "Numeric schedule impact in days. Negative = delay, positive = recovery.",
      width: "130px",
      align: "right" as const,
      renderEdit: (sc) => (
        <div className="space-y-0.5">
          <AutoMetric
            value={sc.impactScheduleValue}
            onSave={(v) => patch(sc.id, "impactScheduleValue", v)}
            unit="d"
            integer
          />
          {sc.impactSchedule && (
            <div
              className="text-[10px] text-muted-foreground/80 italic truncate"
              title={`Legacy note: ${sc.impactSchedule}`}
            >
              {sc.impactSchedule}
            </div>
          )}
        </div>
      ),
      render: (sc) => (
        <div className="text-right">
          <span className="font-mono tabular-nums text-foreground">
            {sc.impactScheduleValue != null ? `${sc.impactScheduleValue} d` : <span className="text-muted-foreground">—</span>}
          </span>
          {sc.impactSchedule && <div className="text-[10px] text-muted-foreground/80 italic truncate" title={sc.impactSchedule}>{sc.impactSchedule}</div>}
        </div>
      ),
    },
    {
      id: "status",
      header: "Status",
      hint: "Current status of the scope change request",
      width: "110px",
      align: "center" as const,
      renderEdit: (sc) => (
        <StatusCell value={sc.status} onSave={(v) => patch(sc.id, "status", v)} />
      ),
      render: (sc) => {
        const s = SCOPE_CHANGE_STATUSES.find((st) => st.key === sc.status) ?? SCOPE_CHANGE_STATUSES[0];
        return (
          <span className={cn("inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium", s.bgColor, s.textColor, s.darkBg, s.darkText)}>
            {s.label}
          </span>
        );
      },
    },
    {
      id: "actions",
      header: "",
      width: "28px",
      render: () => null,
      renderEdit: (sc) => (
        <button
          onClick={() => remove(sc.id)}
          className="opacity-0 group-hover:opacity-100 text-gray-400 hover:text-danger transition-all p-1 rounded"
        >
          <Trash2 size={13} />
        </button>
      ),
    },
  ], [patch, remove]);

  return (
    <div>
      {toolbar && (
        <div className="flex items-center justify-between mb-2">
          <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">Scope Changes</span>
          {toolbar}
        </div>
      )}

      <DataGrid
        columns={columns}
        data={items}
        editable={!readOnly}
        rowKey={(sc) => sc.id}
        emptyMessage="No scope changes yet."
        footer={
          !readOnly && canAdd ? (
            <button
              onClick={add}
              className="flex items-center gap-1.5 w-full px-4 py-2.5 text-[12px] text-muted-foreground
                         hover:text-etex-orange hover:bg-etex-orange-50 transition-colors"
            >
              <Plus size={13} />
              Add scope change{items.length > 0 && <span className="text-gray-300 ml-1">({items.length}/{MAX_SCOPE_CHANGES})</span>}
            </button>
          ) : undefined
        }
      />
    </div>
  );
}
