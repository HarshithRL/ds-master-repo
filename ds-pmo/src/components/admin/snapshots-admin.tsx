"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Camera, ExternalLink, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { DataTable, type DataTableColumn } from "@/components/ui/data-table";
import {
  SNAPSHOT_RAG_COLORS,
  SnapshotRagDot,
} from "@/components/ui/snapshot-rag";
import { TakeSnapshotsDialog } from "./take-snapshots-dialog";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { cn, formatAmount, formatDate } from "@/lib/utils";

import type { Project, ProjectSnapshot, User } from "@/lib/db/models";

type SnapshotRow = ProjectSnapshot & {
  createdBy: Pick<User, "id" | "name" | "email"> | null;
  project: Pick<Project, "id" | "isActive"> | null;
};

const PAGE_SIZE = 50;

const fmt = (n: number | null | undefined) =>
  n == null ? "—" : formatAmount(n, 1);

const RAG_KEYS = [
  "ragProgress",
  "ragSchedule",
  "ragCost",
  "ragRisk",
  "ragScope",
] as const;

/* ─────────────────────────────────────────────────────────────────────
   Detail dialog                                                       */

function SnapshotDetailDialog({
  snapshot,
  open,
  onOpenChange,
}: {
  snapshot: SnapshotRow | null;
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  if (!snapshot) return null;

  const sections = [
    {
      title: "General",
      items: [
        { label: "Project", value: `${snapshot.projectReference} — ${snapshot.projectName}` },
        { label: "Period", value: snapshot.periodLabel },
        { label: "Phase", value: snapshot.currentPhase?.replace(/_/g, " ") ?? "—" },
        { label: "Progress", value: snapshot.progress != null ? `${Math.round(snapshot.progress)}%` : "—" },
        { label: "Taken by", value: snapshot.createdBy?.name ?? "—" },
        { label: "Taken at", value: formatDate(snapshot.createdAt) },
        { label: "Notes", value: snapshot.notes ?? "—" },
      ],
    },
    {
      title: "Budget",
      items: [
        { label: "BAC", value: fmt(snapshot.currentBAC) },
        { label: "EAC", value: fmt(snapshot.eac) },
        { label: "Actuals", value: fmt(snapshot.actualCost) },
        { label: "Committed", value: fmt(snapshot.committed) },
        { label: "Risk Cont. Budgeted", value: fmt(snapshot.riskContingencyBudgeted) },
        { label: "Risk Cont. Consumed", value: fmt(snapshot.riskContingencyConsumed) },
        { label: "Mgmt Cont. Budgeted", value: fmt(snapshot.mgmtContingencyBudgeted) },
        { label: "Mgmt Cont. Consumed", value: fmt(snapshot.mgmtContingencyConsumed) },
      ],
    },
    {
      title: "Schedule & Variance",
      items: [
        { label: "Variance at Completion", value: fmt(snapshot.varianceAtCompletion) },
        { label: "Schedule Buffer", value: snapshot.scheduleBuffer != null ? `${snapshot.scheduleBuffer}d` : "—" },
        { label: "Planned Completion", value: formatDate(snapshot.plannedCompletionDate) },
        { label: "Expected Completion", value: formatDate(snapshot.expectedCompletionDate) },
        { label: "RIDs Open", value: fmt(snapshot.ridsOpen) },
        { label: "Red Flags Open", value: fmt(snapshot.redFlagsOpen) },
      ],
    },
    {
      title: "Risk Summary",
      items: [
        { label: "Open Risks", value: fmt(snapshot.openRiskCount) },
        { label: "Open Issues", value: fmt(snapshot.openIssueCount) },
        { label: "Total Cost at Risk", value: fmt(snapshot.totalCostAtRisk) },
        { label: "Total Time Impact", value: fmt(snapshot.totalTimeImpact) },
      ],
    },
  ];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-base font-semibold">
            Snapshot: {snapshot.projectReference} — {snapshot.periodLabel}
          </DialogTitle>
        </DialogHeader>

        <div className="flex flex-wrap gap-3 py-2">
          <SnapshotRagDot value={snapshot.ragProgress} label="Progress" />
          <SnapshotRagDot value={snapshot.ragSchedule} label="Schedule" />
          <SnapshotRagDot value={snapshot.ragCost} label="Cost" />
          <SnapshotRagDot value={snapshot.ragRisk} label="Risk" />
          <SnapshotRagDot value={snapshot.ragScope} label="Scope" />
        </div>

        <div className="space-y-4">
          {sections.map((section) => (
            <div key={section.title}>
              <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
                {section.title}
              </h4>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
                {section.items.map((item) => (
                  <div key={item.label} className="flex justify-between text-sm">
                    <span className="text-muted-foreground">{item.label}</span>
                    <span className="font-mono text-foreground">{item.value}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        {snapshot.project && (
          <div className="pt-2 border-t">
            <Link
              href={`/projects/${snapshot.project.id}`}
              className="inline-flex items-center gap-1.5 text-xs text-etex-orange hover:underline"
            >
              <ExternalLink className="w-3 h-3" />
              Open project
            </Link>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

/* ─────────────────────────────────────────────────────────────────────
   Main                                                                 */

export function SnapshotsAdmin() {
  const [snapshots, setSnapshots] = useState<SnapshotRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [searchInput, setSearchInput] = useState("");
  const search = useDebouncedValue(searchInput, 300);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<SnapshotRow | null>(null);
  const [taking, setTaking] = useState(false);
  const [showTakeDialog, setShowTakeDialog] = useState(false);
  const [bulkResult, setBulkResult] = useState<{
    total: number;
    created: number;
    updated: number;
    periodLabel: string;
  } | null>(null);

  const currentPeriod = new Date().toISOString().slice(0, 7);

  // Reset to page 1 whenever the (debounced) search term changes.
  useEffect(() => { setPage(1); }, [search]);

  const fetchSnapshots = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        page: String(page),
        limit: String(PAGE_SIZE),
      });
      if (search) params.set("search", search);

      const res = await fetch(`/api/admin/snapshots?${params}`);
      if (!res.ok) throw new Error("Failed to fetch");
      const data = await res.json();
      setSnapshots(data.snapshots);
      setTotal(data.total);
    } catch {
      setSnapshots([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [page, search]);

  useEffect(() => {
    fetchSnapshots();
  }, [fetchSnapshots]);

  async function takeAllSnapshots(periodLabel: string) {
    setTaking(true);
    setBulkResult(null);
    try {
      const res = await fetch("/api/admin/snapshots", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ periodLabel }),
      });
      if (!res.ok) throw new Error("Failed to take snapshots");
      setBulkResult(await res.json());
      fetchSnapshots();
    } catch {
      setBulkResult(null);
    } finally {
      setTaking(false);
    }
  }

  /* ── Columns ── */
  const columns: DataTableColumn<SnapshotRow>[] = [
    {
      key: "periodLabel",
      header: "Period",
      sortable: true,
      sortValue: (r) => r.periodLabel,
      render: (s) => (
        <span className="font-mono font-medium text-foreground">{s.periodLabel}</span>
      ),
      width: "100px",
    },
    {
      key: "projectReference",
      header: "Reference",
      sortable: true,
      sortValue: (r) => r.projectReference,
      render: (s) => (
        <span className="font-mono text-etex-orange">{s.projectReference}</span>
      ),
      width: "120px",
    },
    {
      key: "projectName",
      header: "Project",
      sortable: true,
      sortValue: (r) => r.projectName,
      render: (s) => (
        <span className="truncate max-w-65 inline-block">{s.projectName}</span>
      ),
    },
    {
      key: "currentPhase",
      header: "Phase",
      sortable: true,
      sortValue: (r) => r.currentPhase ?? "",
      render: (s) => (
        <span className="text-muted-foreground">
          {s.currentPhase?.replace(/_/g, " ") ?? "—"}
        </span>
      ),
      hideBelowSm: true,
    },
    {
      key: "progress",
      header: "Progress",
      align: "right",
      numeric: true,
      sortable: true,
      sortValue: (r) => r.progress ?? -1,
      render: (s) => (s.progress != null ? `${Math.round(s.progress)}%` : "—"),
      width: "90px",
      hideBelowSm: true,
    },
    {
      key: "eac",
      header: "EAC",
      align: "right",
      numeric: true,
      sortable: true,
      sortValue: (r) => r.eac ?? 0,
      render: (s) => fmt(s.eac),
      width: "100px",
      hideBelowSm: true,
    },
    {
      key: "varianceAtCompletion",
      header: "Variance",
      align: "right",
      numeric: true,
      sortable: true,
      sortValue: (r) => r.varianceAtCompletion ?? 0,
      render: (s) => (
        <span
          className={cn(
            s.varianceAtCompletion != null && s.varianceAtCompletion > 0 && "text-green-600 dark:text-green-400",
            s.varianceAtCompletion != null && s.varianceAtCompletion < 0 && "text-red-600 dark:text-red-400",
          )}
        >
          {fmt(s.varianceAtCompletion)}
        </span>
      ),
      width: "110px",
      hideBelowSm: true,
    },
    {
      key: "rag",
      header: "RAG",
      align: "center",
      render: (s) => (
        <div className="flex items-center justify-center gap-1">
          {RAG_KEYS.map((key) => {
            const val = s[key] as string | null;
            return val ? (
              <span
                key={key}
                className={cn(
                  "w-2 h-2 rounded-full inline-block",
                  SNAPSHOT_RAG_COLORS[val] ?? "bg-gray-300",
                )}
              />
            ) : null;
          })}
        </div>
      ),
      width: "100px",
    },
    {
      key: "createdBy",
      header: "Taken by",
      sortable: true,
      sortValue: (r) => r.createdBy?.name ?? "",
      render: (s) => (
        <span className="text-xs text-muted-foreground truncate inline-block max-w-30">
          {s.createdBy?.name ?? "—"}
        </span>
      ),
      hideBelowSm: true,
    },
    {
      key: "createdAt",
      header: "Date",
      sortable: true,
      sortValue: (r) => new Date(r.createdAt),
      render: (s) => (
        <span className="text-xs font-mono text-muted-foreground">
          {formatDate(s.createdAt)}
        </span>
      ),
      width: "130px",
      hideBelowSm: true,
    },
  ];

  return (
    <>
      <DataTable
        columns={columns}
        data={snapshots}
        rowKey={(s) => s.id}
        loading={loading}
        emptyTitle="No snapshots"
        emptyMessage="Take a snapshot for the current period to start tracking history."
        emptyIcon={<Camera className="w-4 h-4" />}
        onRowClick={setSelected}
        manualSort
        toolbar={{
          search: {
            value: searchInput,
            onChange: setSearchInput,
            placeholder: "Search by project or period...",
          },
          actions: (
            <Button
              onClick={() => setShowTakeDialog(true)}
              disabled={taking}
              className="bg-etex-orange hover:bg-etex-orange-dark text-white text-xs h-8 shrink-0"
            >
              {taking ? (
                <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
              ) : (
                <Camera className="w-3.5 h-3.5 mr-1.5" />
              )}
              Take All Snapshots ({currentPeriod})
            </Button>
          ),
          extra: bulkResult && (
            <div className="text-xs text-muted-foreground">
              <span className="font-medium text-foreground">{bulkResult.total}</span> projects —{" "}
              <span className="text-green-600 dark:text-green-400">
                {bulkResult.created} created
              </span>
              ,{" "}
              <span className="text-blue-600 dark:text-blue-400">
                {bulkResult.updated} updated
              </span>{" "}
              for {bulkResult.periodLabel}
            </div>
          ),
        }}
        pagination={{
          page,
          pageSize: PAGE_SIZE,
          total,
          onPageChange: setPage,
        }}
      />

      <SnapshotDetailDialog
        snapshot={selected}
        open={!!selected}
        onOpenChange={(v) => !v && setSelected(null)}
      />

      <TakeSnapshotsDialog
        open={showTakeDialog}
        onOpenChange={setShowTakeDialog}
        onConfirm={(period) => {
          setShowTakeDialog(false);
          takeAllSnapshots(period);
        }}
        taking={taking}
      />
    </>
  );
}
