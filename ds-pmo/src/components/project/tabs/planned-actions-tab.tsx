"use client";

import { useMemo, useRef, useState, useEffect, memo } from "react";
import { Plus, Trash2 } from "lucide-react";
import { cn, formatDate } from "@/lib/utils";
import { AutoInput, AutoGrowInput, AutoDateInput } from "@/components/ui/auto-fields";
import { DataGrid, type DataGridColumn } from "@/components/ui/data-grid";
import { useOptimisticList } from "@/hooks/use-optimistic-list";
import { useReadOnly } from "@/components/ui/read-only-context";
import type { PlannedAction } from "@/lib/db/models";

/* ── Status definitions ───────────────────────────────────────────── */

const STATUSES = [
  { key: "OPEN",        label: "Open",        bgColor: "bg-blue-100",     textColor: "text-blue-700",     darkBg: "dark:bg-blue-900/30",     darkText: "dark:text-blue-300" },
  { key: "IN_PROGRESS", label: "In Progress", bgColor: "bg-amber-100",    textColor: "text-amber-700",    darkBg: "dark:bg-amber-900/30",    darkText: "dark:text-amber-300" },
  { key: "COMPLETED",   label: "Completed",   bgColor: "bg-emerald-100",  textColor: "text-emerald-700",  darkBg: "dark:bg-emerald-900/30",  darkText: "dark:text-emerald-300" },
  { key: "CANCELLED",   label: "Cancelled",   bgColor: "bg-red-100",      textColor: "text-red-700",      darkBg: "dark:bg-red-900/30",      darkText: "dark:text-red-300" },
] as const;

const StatusCell = memo(function StatusCell({
  value,
  onSave,
}: {
  value: string;
  onSave: (v: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const status = STATUSES.find((s) => s.key === value) ?? STATUSES[0];

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
        <div className="absolute z-30 top-full left-0 mt-1 dropdown-surface rounded py-1 min-w-32">
          {STATUSES.map((s) => (
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

/* ── Main tab ─────────────────────────────────────────────────────── */

const MAX_ACTIONS = 30;

interface Props {
  projectId: string;
  plannedActions: PlannedAction[];
}

export function PlannedActionsTab({ projectId, plannedActions }: Props) {
  const readOnly = useReadOnly();
  const baseUrl = `/api/projects/${projectId}/planned-actions`;

  const createOptimistic = useMemo(
    () => (): PlannedAction => ({
      id: `_tmp_${Date.now()}`,
      projectId,
      action: "",
      ownerLabel: null,
      byDate: null,
      status: "OPEN",
      notes: null,
      sortOrder: plannedActions.length,
      createdAt: new Date(),
      updatedAt: new Date(),
    }),
    [projectId, plannedActions.length],
  );

  const createPayload = useMemo(
    () => () => ({ action: "New action", status: "OPEN" }),
    [],
  );

  const { items, add, patch, remove } = useOptimisticList<PlannedAction>({
    initial: plannedActions,
    baseUrl,
    createOptimistic,
    createPayload,
  });

  const canAdd = items.length < MAX_ACTIONS;

  const columns: DataGridColumn<PlannedAction>[] = useMemo(() => [
    {
      id: "action",
      header: "Action",
      hint: "What needs to happen",
      width: "minmax(0,2fr)",
      renderEdit: (a) => (
        <AutoGrowInput
          value={a.action}
          onSave={(v) => patch(a.id, "action", v)}
          placeholder="Describe the planned action…"
          maxRows={3}
        />
      ),
      render: (a) => <span className="text-foreground">{a.action || <span className="text-muted-foreground">—</span>}</span>,
    },
    {
      id: "ownerLabel",
      header: "Owner",
      hint: "Team or person responsible (free-text)",
      width: "180px",
      renderEdit: (a) => (
        <AutoInput
          value={a.ownerLabel ?? ""}
          onSave={(v) => patch(a.id, "ownerLabel", v || null)}
          placeholder="e.g. PLW team / Alberto O. (IT)"
        />
      ),
      render: (a) => <span className="text-foreground">{a.ownerLabel || <span className="text-muted-foreground">—</span>}</span>,
    },
    {
      id: "byDate",
      header: "By",
      hint: "Target completion date",
      width: "120px",
      renderEdit: (a) => (
        <AutoDateInput value={a.byDate} onSave={(v) => patch(a.id, "byDate", v)} />
      ),
      render: (a) => (
        <span className="text-foreground font-mono text-xs tabular-nums">
          {a.byDate ? formatDate(a.byDate) : <span className="text-muted-foreground">—</span>}
        </span>
      ),
    },
    {
      id: "status",
      header: "Status",
      width: "120px",
      align: "center" as const,
      renderEdit: (a) => <StatusCell value={a.status} onSave={(v) => patch(a.id, "status", v)} />,
      render: (a) => {
        const s = STATUSES.find((st) => st.key === a.status) ?? STATUSES[0];
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
      renderEdit: (a) => (
        <button
          onClick={() => remove(a.id)}
          className="opacity-0 group-hover:opacity-100 text-gray-400 hover:text-danger transition-all p-1 rounded"
        >
          <Trash2 size={13} />
        </button>
      ),
    },
  ], [patch, remove]);

  return (
    <DataGrid
      columns={columns}
      data={items}
      editable={!readOnly}
      rowKey={(a) => a.id}
      emptyMessage="No planned actions yet."
      footer={
        !readOnly && canAdd ? (
          <button
            onClick={add}
            className="flex items-center gap-1.5 w-full px-4 py-2.5 text-[12px] text-muted-foreground hover:text-etex-orange hover:bg-etex-orange-50 transition-colors"
          >
            <Plus size={13} />
            Add planned action{items.length > 0 && <span className="text-gray-300 ml-1">({items.length}/{MAX_ACTIONS})</span>}
          </button>
        ) : undefined
      }
    />
  );
}
