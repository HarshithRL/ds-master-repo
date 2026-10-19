"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { cn, formatAmount } from "@/lib/utils";
import { deriveProjectYears } from "@/lib/calculations";
import { api } from "@/lib/api";
import { AutoAmount } from "@/components/ui/auto-fields";
import { DataGrid, type DataGridColumn } from "@/components/ui/data-grid";
import { useSaveStatus } from "@/hooks/use-save-status";
import { useReadOnly } from "@/components/ui/read-only-context";
import type { BudgetLine } from "@/lib/db/models";

/* ── Types ────────────────────────────────────────────────────────── */

interface BudgetBreakdownTabProps {
  projectId: string;
  createdAt: string | Date;
  actualStartDate?: string | Date | null;
  plannedCompletionDate?: string | Date | null;
  expectedCompletionDate?: string | Date | null;
  onBacChanged?: (bac: number) => void;
}

type LineType = "CAPEX" | "OPEX";

type BreakdownRow = {
  id: string;
  label: string;
  type: LineType | "TOTAL";
  amounts: Record<number, number>;
  total: number;
};

/* ── Helpers ──────────────────────────────────────────────────────── */

function getAmount(lines: BudgetLine[], type: LineType, year: number): number {
  return lines.find((l) => l.type === type && l.year === year)?.amount ?? 0;
}

function sumByYear(lines: BudgetLine[], year: number): number {
  return lines.filter((l) => l.year === year).reduce((s, l) => s + l.amount, 0);
}

function sumByType(lines: BudgetLine[], type: LineType): number {
  return lines.filter((l) => l.type === type).reduce((s, l) => s + l.amount, 0);
}

function sumAll(lines: BudgetLine[]): number {
  return lines.reduce((s, l) => s + l.amount, 0);
}

/* ── Formatted read-only cell — sizing matches Summary's ComputedAmount ─── */

function AmountCell({ value, bold }: { value: number; bold?: boolean }) {
  return (
    <span className={`font-mono text-sm tabular-nums ${bold ? "font-semibold" : "font-medium"}`}>
      {formatAmount(value, 1)}
      <span className="ml-0.5 text-[10px] text-muted-foreground font-semibold tracking-wide">k€</span>
    </span>
  );
}

/* ═══════════════════════════════════════════════════════════════════ */

export function BudgetBreakdownTab({
  projectId,
  createdAt,
  actualStartDate,
  plannedCompletionDate,
  expectedCompletionDate,
  onBacChanged,
}: BudgetBreakdownTabProps) {
  const readOnly = useReadOnly();
  const [lines, setLines] = useState<BudgetLine[]>([]);
  const { saving, saved, saveFailed } = useSaveStatus();
  const years = useMemo(
    () => deriveProjectYears({
      actualStartDate: actualStartDate ?? null,
      plannedCompletionDate: plannedCompletionDate ?? null,
      expectedCompletionDate: expectedCompletionDate ?? null,
      createdAt,
    }),
    [actualStartDate, plannedCompletionDate, expectedCompletionDate, createdAt],
  );

  const fetchLines = useCallback(async () => {
    try {
      const data = await api.get(`/api/projects/${projectId}/budget/lines`);
      setLines(data as BudgetLine[]);
    } catch { /* ignore */ }
  }, [projectId]);

  useEffect(() => { fetchLines(); }, [fetchLines]);

  const upsert = async (type: LineType, year: number, amount: number) => {
    // Optimistic update
    setLines((prev) => {
      const idx = prev.findIndex((l) => l.type === type && l.year === year);
      if (idx >= 0) {
        const updated = [...prev];
        updated[idx] = { ...updated[idx], amount };
        return updated;
      }
      return [...prev, { id: "", budgetId: "", type, year, amount } as BudgetLine];
    });

    saving();
    try {
      const res = await api.put(`/api/projects/${projectId}/budget/lines`, { type, year, amount });
      onBacChanged?.((res as { bac: number }).bac);
      saved();
    } catch {
      saveFailed();
      fetchLines();
    }
  };

  /* ── Build rows for the DataGrid ──────────────────────────────── */

  const rows: BreakdownRow[] = useMemo(() => {
    const opexAmounts: Record<number, number> = {};
    const capexAmounts: Record<number, number> = {};
    const totalAmounts: Record<number, number> = {};

    for (const y of years) {
      opexAmounts[y] = getAmount(lines, "OPEX", y);
      capexAmounts[y] = getAmount(lines, "CAPEX", y);
      totalAmounts[y] = sumByYear(lines, y);
    }

    return [
      { id: "opex", label: "OPEX", type: "OPEX" as const, amounts: opexAmounts, total: sumByType(lines, "OPEX") },
      { id: "capex", label: "CAPEX", type: "CAPEX" as const, amounts: capexAmounts, total: sumByType(lines, "CAPEX") },
      { id: "total", label: "Total (BAC)", type: "TOTAL" as const, amounts: totalAmounts, total: sumAll(lines) },
    ];
  }, [lines, years]);

  /* ── DataGrid columns ─────────────────────────────────────────── */

  /* Column-intrinsic classes (border / tint / horizontal padding / alignment)
     so the header bar and every data cell pick up the exact same column rules.
     Vertical padding is left to the row wrapper (header gets py-2, dg-row CSS
     handles data rows) so heights stay distinct without affecting alignment. */
  const columns: DataGridColumn<BreakdownRow>[] = useMemo(() => {
    const cols: DataGridColumn<BreakdownRow>[] = [
      {
        id: "category",
        header: "Breakdown — BAC",
        width: "minmax(140px, 1fr)",
        cellClassName: "px-3 flex items-center",
        render: (row) => (
          <span className={cn(
            "text-[12px]",
            row.type === "TOTAL" ? "font-bold text-foreground" : "font-medium text-muted-foreground uppercase tracking-wide",
          )}>
            {row.label}
          </span>
        ),
      },
      ...years.map((y, idx) => ({
        id: `year-${y}`,
        header: String(y),
        width: "minmax(90px, 1fr)",
        align: "right" as const,
        cellClassName: cn(
          "border-l border-border/40 px-2 flex items-center justify-end",
          idx % 2 === 1 && "bg-muted/20",
        ),
        render: (row: BreakdownRow) => <AmountCell value={row.amounts[y] ?? 0} bold={row.type === "TOTAL"} />,
        renderEdit: (row: BreakdownRow) =>
          row.type === "TOTAL" ? (
            <AmountCell value={row.amounts[y] ?? 0} bold />
          ) : (
            <AutoAmount
              value={row.amounts[y] ?? 0}
              onSave={(v) => upsert(row.type as LineType, y, v)}
              decimals={1}
              unit="k€"
            />
          ),
      })),
      {
        id: "total",
        header: "Total",
        width: "minmax(100px, 1fr)",
        align: "right" as const,
        cellClassName: "border-l-2 border-border/60 px-2 flex items-center justify-end bg-muted/30",
        render: (row) => <AmountCell value={row.total} bold />,
      },
    ];
    return cols;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [years, lines, readOnly]);

  /* Custom merged header. Uses the same grid template AND the same column
     classes as the data rows (cellClassName) — that's what guarantees every
     vertical separator lines up exactly with the border below it. */
  const gridTemplate = columns.map((c) => c.width).join(" ");
  const breakdownHeader = (
    <div
      className="grid items-stretch gap-2 border-b border-border bg-muted/30"
      style={{ gridTemplateColumns: gridTemplate, padding: "0 12px" }}
    >
      {columns.map((col) => (
        <div key={col.id} className={cn("py-2", col.cellClassName)}>
          <span className={cn(
            "text-[11px] font-bold uppercase tracking-wider text-muted-foreground",
            col.align === "right" && "ml-auto",
          )}>
            {col.header}
          </span>
        </div>
      ))}
    </div>
  );

  return (
    <DataGrid
      columns={columns}
      data={rows}
      editable={!readOnly}
      rowKey={(r) => r.id}
      rowClassName={(r) => r.type === "TOTAL" ? "!bg-muted/40 !font-bold border-t-2" : ""}
      header={breakdownHeader}
      hideHeader
    />
  );
}
