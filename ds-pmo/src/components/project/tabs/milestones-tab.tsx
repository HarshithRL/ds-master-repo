"use client";

import { useMemo } from "react";
import { Plus, Trash2 } from "lucide-react";
import { cn, formatDate, getVarianceDays } from "@/lib/utils";
import { AutoInput, AutoDateInput } from "@/components/ui/auto-fields";
import { DataGrid, type DataGridColumn } from "@/components/ui/data-grid";
import { useOptimisticList } from "@/hooks/use-optimistic-list";
import { useReadOnly } from "@/components/ui/read-only-context";
import type { Milestone } from "@/lib/db/models";

/* ═══════════════════════════════════════════════════════════════════
   MilestonesTab
   ═══════════════════════════════════════════════════════════════════ */

interface MilestonesTabProps {
  projectId: string;
  milestones: Milestone[];
}

export function MilestonesTab({ projectId, milestones: propMilestones }: MilestonesTabProps) {
  const readOnly = useReadOnly();
  const baseUrl = `/api/projects/${projectId}/milestones`;

  const createOptimistic = useMemo(
    () => () =>
      ({
        id: `_tmp_${Date.now()}`,
        projectId,
        name: "",
        targetDate: null,
        expectedDate: null,
        remarks: null,
        createdAt: new Date(),
        updatedAt: new Date(),
      }) as Milestone,
    [projectId],
  );

  const createPayload = useMemo(
    () => () => ({ name: "" }),
    [],
  );

  const { items, add, patch, remove } = useOptimisticList<Milestone>({
    initial: propMilestones,
    baseUrl,
    createOptimistic,
    createPayload,
  });

  const columns: DataGridColumn<Milestone>[] = useMemo(() => [
    {
      id: "name",
      header: "Milestone",
      hint: "Key deliverable or checkpoint name",
      width: "minmax(0,2fr)",
      renderEdit: (m) => (
        <AutoInput value={m.name} onSave={(v) => patch(m.id, "name", v)} placeholder="Milestone name" />
      ),
      render: (m) => <span className="text-foreground">{m.name || <span className="text-muted-foreground">—</span>}</span>,
    },
    {
      id: "targetDate",
      header: "Target",
      hint: "Originally planned date for this milestone",
      width: "120px",
      renderEdit: (m) => <AutoDateInput value={m.targetDate} onSave={(v) => patch(m.id, "targetDate", v)} />,
      render: (m) => {
        if (!m.targetDate) return <span className="text-muted-foreground">—</span>;
        return (
          <span className="font-mono text-muted-foreground text-sm">
            {formatDate(m.targetDate)}
          </span>
        );
      },
    },
    {
      id: "expectedDate",
      header: "Expected",
      hint: "Current forecast date — drives variance calculation",
      width: "120px",
      renderEdit: (m) => <AutoDateInput value={m.expectedDate} onSave={(v) => patch(m.id, "expectedDate", v)} />,
      render: (m) => {
        if (!m.expectedDate) return <span className="text-muted-foreground">—</span>;
        return (
          <span className="font-mono text-muted-foreground text-sm">
            {formatDate(m.expectedDate)}
          </span>
        );
      },
    },
    {
      id: "variance",
      header: "Var.",
      hint: "Days difference between target and expected (positive = late)",
      width: "70px",
      align: "right",
      render: (m) => {
        const variance = getVarianceDays(
          m.targetDate ? new Date(m.targetDate) : null,
          m.expectedDate ? new Date(m.expectedDate) : (m.targetDate ? new Date(m.targetDate) : null),
        );
        return (
          <div className="h-9 flex items-center justify-end px-2 rounded-sm computed-row">
            <span
              className={cn(
                "font-mono text-sm font-semibold tabular-nums",
                variance != null && variance > 0 && "text-danger",
                variance != null && variance < 0 && "text-success",
                (variance == null || variance === 0) && "text-muted-foreground",
              )}
            >
              {variance != null && variance !== 0 ? `${variance > 0 ? "+" : ""}${variance}d` : "—"}
            </span>
          </div>
        );
      },
      renderEdit: undefined,
    },
    {
      id: "remarks",
      header: "Remarks",
      hint: "Notes or context about this milestone's status",
      width: "minmax(0,1fr)",
      renderEdit: (m) => (
        <AutoInput value={m.remarks ?? ""} onSave={(v) => patch(m.id, "remarks", v || null)} placeholder="—" />
      ),
      render: (m) => <span className="text-foreground">{m.remarks || <span className="text-muted-foreground">—</span>}</span>,
    },
    {
      id: "actions",
      header: "",
      width: "28px",
      render: () => null,
      renderEdit: (m) => (
        <button
          onClick={() => remove(m.id)}
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
      rowKey={(m) => m.id}
      emptyMessage="No milestones yet."
      footer={
        !readOnly ? (
          <button
            onClick={add}
            className="flex items-center gap-1.5 w-full px-4 py-2.5 text-[12px] text-muted-foreground
                       hover:text-etex-orange hover:bg-etex-orange-50 transition-colors"
          >
            <Plus size={13} />
            Add milestone
          </button>
        ) : undefined
      }
    />
  );
}
