"use client";

import { useState, useEffect } from "react";
import { Check, Hourglass } from "lucide-react";
import { cn, formatDate } from "@/lib/utils";
import { api } from "@/lib/api";
import { AutoInput, AutoDateInput, RowLabel } from "@/components/ui/auto-fields";
import { DataGrid, type DataGridColumn } from "@/components/ui/data-grid";
import { useSaveStatus } from "@/hooks/use-save-status";
import { useReadOnly } from "@/components/ui/read-only-context";
import { GATES } from "@/lib/constants";
import type { GateRecord } from "@/lib/db/models";

/* ── Types ──────────────────────────────────────────────────────── */

type DisplayGate = {
  id: string | undefined;
  gateKey: string;
  label: string;
  color: string;
  status: string;
  plannedDate: Date | string | null;
  completedDate: Date | string | null;
  notes: string;
};

/* ── Status pill — Passed / Planned indicator and toggle ───────────── */

function StatusPill({
  isPassed,
  onClick,
  title,
}: {
  isPassed: boolean;
  onClick?: () => void;
  title?: string;
}) {
  const Icon = isPassed ? Check : Hourglass;
  const interactive = Boolean(onClick);

  return (
    <div className="flex h-9 items-center justify-center">
      <button
        type="button"
        onClick={onClick}
        disabled={!interactive}
        title={title}
        aria-pressed={isPassed}
        className={cn(
          "group inline-flex h-7 items-center gap-1.5 rounded-sm px-2.5 text-[11px] font-semibold",
          "transition-all duration-150 ease-out",
          "ring-1 ring-inset",
          interactive && "cursor-pointer active:scale-[0.97]",
          !interactive && "cursor-default",
          isPassed
            ? cn(
                "bg-green-100 text-green-700 ring-green-600/20",
                "dark:bg-green-500/15 dark:text-green-300 dark:ring-green-400/30",
                interactive && "hover:bg-green-200 hover:ring-green-600/40 dark:hover:bg-green-500/25",
              )
            : cn(
                "bg-secondary text-muted-foreground ring-border",
                interactive && "hover:bg-muted hover:text-foreground hover:ring-foreground/20",
              ),
        )}
      >
        <Icon
          className={cn(
            "h-3.5 w-3.5 shrink-0 transition-transform duration-150",
            isPassed ? "stroke-3" : "stroke-2",
            interactive && "group-hover:scale-110",
          )}
          aria-hidden
        />
        <span>{isPassed ? "Passed" : "Planned"}</span>
      </button>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   GatesTab — budget-style row layout, connected to timeline
   ═══════════════════════════════════════════════════════════════════ */

interface GatesTabProps {
  projectId: string;
  gates: GateRecord[];
  hoveredGate?: string | null;
  onRowHover?: (gateKey: string | null) => void;
}

export function GatesTab({ projectId, gates: propGates, hoveredGate, onRowHover }: GatesTabProps) {
  const readOnly = useReadOnly();
  const { saving, saved, saveFailed } = useSaveStatus();

  const buildDisplayGates = (gateRecords: GateRecord[]): DisplayGate[] =>
    GATES.map((def) => {
      const rec = (gateRecords ?? []).find((g) => g.gate === def.key);
      return {
        id: rec?.id,
        gateKey: def.key,
        label: def.label,
        color: def.color,
        status: rec?.status ?? "PLANNED",
        plannedDate: rec?.plannedDate ?? null,
        completedDate: rec?.completedDate ?? null,
        notes: rec?.notes ?? "",
      };
    });

  const [displayGates, setDisplayGates] = useState<DisplayGate[]>(() => buildDisplayGates(propGates));

  useEffect(() => setDisplayGates(buildDisplayGates(propGates)), [propGates]);

  /* ── Patch a single gate field (optimistic) ────────────────── */

  const patchGate = async (gateKey: string, field: string, value: unknown) => {
    const gate = displayGates.find((g) => g.gateKey === gateKey);
    if (!gate) return;

    const prevValue = (gate as Record<string, unknown>)[field];
    setDisplayGates((prev) =>
      prev.map((g) => (g.gateKey === gateKey ? { ...g, [field]: value } : g)),
    );
    saving();

    try {
      await api.put(`/api/projects/${projectId}/gates`, { gate: gateKey, status: gate.status, [field]: value });
      saved();
    } catch {
      // Revert only the changed field
      setDisplayGates((prev) =>
        prev.map((g) => (g.gateKey === gateKey ? { ...g, [field]: prevValue } : g)),
      );
      saveFailed();
    }
  };

  /* ── Toggle ONE gate's status — never touches sibling gates ──── */

  const toggleGateStatus = async (clickedGateKey: string) => {
    const gate = displayGates.find((g) => g.gateKey === clickedGateKey);
    if (!gate) return;

    const willPass = gate.status !== "PASSED";
    // When passing for the first time and no completion date is set yet,
    // default to the existing planned date (preserves the user's entry),
    // falling back to today. Does NOT overwrite an existing completedDate.
    const seededCompletedDate =
      willPass && !gate.completedDate
        ? gate.plannedDate
          ? (gate.plannedDate instanceof Date ? gate.plannedDate.toISOString() : new Date(gate.plannedDate).toISOString())
          : new Date().toISOString()
        : gate.completedDate;

    const snapshot = gate;

    // Optimistic — only this row changes
    setDisplayGates((prev) =>
      prev.map((g) =>
        g.gateKey === clickedGateKey
          ? { ...g, status: willPass ? "PASSED" : "PLANNED", completedDate: seededCompletedDate }
          : g,
      ),
    );
    saving();

    const body: Record<string, unknown> = {
      gate: clickedGateKey,
      status: willPass ? "PASSED" : "PLANNED",
    };
    // Only send completedDate when we're seeding it on first pass. Toggling
    // back to PLANNED preserves the previous completedDate in the DB.
    if (willPass && !gate.completedDate && seededCompletedDate) {
      body.completedDate = seededCompletedDate;
    }

    try {
      await api.put(`/api/projects/${projectId}/gates`, body);
      saved();
    } catch {
      setDisplayGates((prev) =>
        prev.map((g) => (g.gateKey === clickedGateKey ? snapshot : g)),
      );
      saveFailed();
    }
  };

  /* ── DataGrid columns ─────────────────────────────────────── */

  const columns: DataGridColumn<DisplayGate>[] = [
    {
      id: "gate",
      header: "Gate",
      hint: "Phase-gate checkpoint in the project lifecycle",
      width: "1fr",
      render: (gate) => (
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: gate.color }} />
          <RowLabel>{gate.label}</RowLabel>
        </div>
      ),
    },
    {
      id: "date",
      header: "Date",
      hint: "Planned date when not yet passed; actual date once passed. Editable in both states — toggling status doesn't overwrite a date you've already entered.",
      width: "150px",
      render: (gate) => {
        const isPassed = gate.status === "PASSED";
        const value = isPassed ? gate.completedDate : gate.plannedDate;
        return (
          <div className="h-9 flex items-center px-2.5">
            {value ? (
              <span className={cn(
                "text-sm font-mono tabular-nums",
                isPassed ? "text-success" : "text-foreground",
              )}>
                {formatDate(value)}
              </span>
            ) : (
              <span className="text-sm text-muted-foreground">—</span>
            )}
          </div>
        );
      },
      renderEdit: (gate) => {
        const isPassed = gate.status === "PASSED";
        const field = isPassed ? "completedDate" : "plannedDate";
        const value = isPassed ? gate.completedDate : gate.plannedDate;
        return (
          <AutoDateInput
            value={value}
            onSave={(v) => patchGate(gate.gateKey, field, v)}
            className={cn(
              "transition-colors duration-150",
              isPassed && "text-success focus:text-success",
            )}
          />
        );
      },
    },
    {
      id: "status",
      header: "Status",
      hint: "Click to toggle this gate between Planned and Passed. Affects only this row — other gates are independent.",
      width: "96px",
      align: "center",
      render: (gate) => {
        const isPassed = gate.status === "PASSED";
        if (readOnly) return <StatusPill isPassed={isPassed} />;
        return (
          <StatusPill
            isPassed={isPassed}
            onClick={() => toggleGateStatus(gate.gateKey)}
            title={isPassed ? "Click to mark as Planned" : "Click to mark as Passed"}
          />
        );
      },
    },
    {
      id: "notes",
      header: "Notes",
      hint: "Decisions, conditions, or comments from the gate review",
      width: "minmax(0,1.2fr)",
      render: (gate) => <span className="text-foreground">{gate.notes || <span className="text-muted-foreground">—</span>}</span>,
      renderEdit: (gate) => (
        <AutoInput
          value={gate.notes}
          onSave={(v) => patchGate(gate.gateKey, "notes", v)}
          placeholder="—"
        />
      ),
    },
  ];

  return (
    <DataGrid
      columns={columns}
      data={displayGates}
      editable={!readOnly}
      rowKey={(g) => g.gateKey}
      onRowHover={onRowHover ? (gate) => onRowHover(gate?.gateKey ?? null) : undefined}
      rowStyle={(gate) => {
        const isHovered = hoveredGate === gate.gateKey;
        if (isHovered) return { backgroundColor: "var(--color-etex-orange-50)" };
        return { backgroundColor: `${gate.color}18` };
      }}
    />
  );
}
