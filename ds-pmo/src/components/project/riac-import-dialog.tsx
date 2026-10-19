"use client";

import { useState, useMemo, useRef, useCallback } from "react";
import {
  Upload,
  AlertTriangle,
  Check,
  Loader2,
  ChevronRight,
  ShieldAlert,
  Repeat,
  ArrowRight,
  CheckCircle2,
} from "lucide-react";
import { cn, formatAmount } from "@/lib/utils";
import { toast, reportApiError } from "@/lib/toast";
import { IMPACT_STYLE, IMPACT_LABEL } from "./tabs/risks-tab";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import type {
  ParsedRisk,
  ParsedAction,
  RiacPreview,
} from "@/app/api/projects/[id]/risks/import/route";

/* ── Types ─────────────────────────────────────────────────────── */

type Tab = "risks" | "changes";

type DialogState =
  | { step: "idle" }
  | { step: "parsing" }
  | { step: "error"; message: string }
  | { step: "preview"; data: RiacPreview };

interface RiacImportDialogProps {
  projectId: string;
  onImported: () => void;
}

/* ── Helpers ───────────────────────────────────────────────────── */

function weightToImpact(type: string, weight: number): string {
  if (type.toLowerCase() === "issue") return "ISSUE";
  if (weight >= 8) return "HIGH";
  if (weight >= 3) return "MODERATE";
  return "LOW";
}

/* ── KPI Cell ──────────────────────────────────────────────────── */

function Kpi({ label, value, color, dot, suffix }: {
  label: string;
  value: number;
  color?: string;
  dot?: string;
  suffix?: string;
}) {
  return (
    <div className="bg-white dark:bg-[#21252B] px-3 py-2.5">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-gray-400 mb-0.5 flex items-center gap-1">
        {dot && <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", dot)} />}
        {label}
      </div>
      <div className="flex items-baseline gap-0.5">
        <span className={cn("text-lg font-bold font-mono tabular-nums leading-tight", color ?? "text-gray-800 dark:text-gray-200")}>
          {formatAmount(value, 1)}
        </span>
        {suffix && <span className="text-[10px] font-semibold text-gray-400">{suffix}</span>}
      </div>
    </div>
  );
}

/* ── Checkbox ──────────────────────────────────────────────────── */

function Tick({ checked }: { checked: boolean }) {
  return (
    <div className={cn(
      "w-4 h-4 rounded border-[1.5px] flex items-center justify-center transition-all shrink-0",
      checked ? "bg-etex-orange border-etex-orange scale-105" : "border-gray-300 bg-white dark:border-gray-600 dark:bg-gray-800",
    )}>
      {checked && <Check size={10} className="text-white" strokeWidth={3} />}
    </div>
  );
}

/* ── Action status badge ──────────────────────────────────────── */

function ActionStatusBadge({ status }: { status: string }) {
  const s = status.toLowerCase();
  const color = s.includes("close") ? "bg-gray-100 text-gray-500"
    : s.includes("progress") ? "bg-amber-50 text-amber-700"
    : s.includes("delay") ? "bg-red-50 text-red-600"
    : "bg-blue-50 text-blue-600";
  return (
    <span className={cn("text-[9px] font-semibold px-1.5 py-0.5 rounded-sm uppercase tracking-wide", color)}>
      {status || "—"}
    </span>
  );
}

/* ── Change status badge ─────────────────────────────────────── */

function ChangeStatusBadge({ status }: { status: string }) {
  const s = status.toLowerCase();
  const color = s.includes("hold")
    ? "bg-amber-50 text-amber-700"
    : s.includes("cancel") || s.includes("closed")
      ? "bg-red-50 text-red-600"
      : "bg-blue-50 text-blue-600";
  return (
    <span className={cn("text-[9px] font-semibold px-1.5 py-0.5 rounded-sm uppercase tracking-wide whitespace-nowrap", color)}>
      {status || "—"}
    </span>
  );
}

/* ── Risk row with nested actions ─────────────────────────────── */

function RiskCard({
  risk,
  actions,
  selected,
  onToggle,
}: {
  risk: ParsedRisk;
  actions: ParsedAction[];
  selected: boolean;
  onToggle: () => void;
}) {
  const imp = weightToImpact(risk.type, risk.weight);
  const style = IMPACT_STYLE[imp] ?? IMPACT_STYLE.MODERATE;
  const hasActions = actions.length > 0;

  return (
    <div className={cn(
      "border-b border-gray-100 dark:border-gray-800 last:border-0 transition-colors",
      selected ? "bg-etex-orange-50/60 dark:bg-etex-orange/5" : "hover:bg-gray-50/50 dark:hover:bg-gray-800/30",
    )}>
      <div
        onClick={onToggle}
        className="grid items-start gap-2.5 px-3 py-2.5 cursor-pointer"
        style={{ gridTemplateColumns: "20px minmax(0,1fr) 68px 40px 52px 52px 72px" }}
      >
        <div className="pt-0.5"><Tick checked={selected} /></div>

        <div className="min-w-0">
          <span className="text-xs text-gray-800 dark:text-gray-200 leading-snug whitespace-pre-wrap wrap-break-word">
            {risk.description}
          </span>
          {risk.owner && (
            <span className="block text-[10px] text-gray-400 mt-0.5">{risk.owner}</span>
          )}
        </div>

        <div className={cn(
          "flex items-center justify-center px-1 py-1 rounded-sm text-[10px] font-bold uppercase tracking-wide self-start",
          style.bg, style.fg,
        )}>
          {IMPACT_LABEL[imp] ?? imp}
        </div>

        <span className="text-center font-mono font-semibold text-gray-500 text-xs tabular-nums pt-0.5">
          {risk.weight}
        </span>
        <span className="text-right font-mono text-gray-500 text-xs tabular-nums pt-0.5">
          {risk.costK != null ? risk.costK : "—"}
        </span>
        <span className="text-right font-mono text-gray-500 text-xs tabular-nums pt-0.5">
          {risk.timeImpactDays != null ? risk.timeImpactDays : "—"}
        </span>
        <span className="text-right text-[10px] text-gray-400 pt-0.5">
          {hasActions ? `${actions.length} action${actions.length !== 1 ? "s" : ""}` : ""}
        </span>
      </div>

      {selected && hasActions && (
        <div className="ml-8 mr-3 mb-2.5 border border-gray-200 dark:border-gray-700 rounded bg-white dark:bg-[#21252B] overflow-hidden">
          <div className="grid items-center gap-2 px-2.5 py-1 bg-gray-50/80 dark:bg-gray-800/50 text-[9px] font-semibold uppercase tracking-wider text-gray-400"
            style={{ gridTemplateColumns: "minmax(0,1fr) 60px 64px 52px" }}
          >
            <span>Action</span>
            <span>Response</span>
            <span>Assigned</span>
            <span className="text-center">Status</span>
          </div>
          {actions.map((a, i) => (
            <div
              key={`${a.riskNum}-${a.actionNum}-${i}`}
              className="grid items-start gap-2 px-2.5 py-1.5 text-xs border-t border-gray-100 dark:border-gray-800 hover:bg-gray-50/40 dark:hover:bg-gray-800/20 transition-colors"
              style={{ gridTemplateColumns: "minmax(0,1fr) 60px 64px 52px" }}
            >
              <span className="text-gray-700 dark:text-gray-300 leading-snug whitespace-pre-wrap wrap-break-word flex items-start gap-1">
                <ChevronRight size={10} className="text-gray-300 shrink-0 mt-0.5" />
                {a.action}
              </span>
              <span className="text-[10px] text-gray-500 wrap-break-word">{a.response || "—"}</span>
              <span className="text-[10px] text-gray-500 wrap-break-word">{a.assignedTo || "—"}</span>
              <div className="text-center"><ActionStatusBadge status={a.status} /></div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── Success banner ───────────────────────────────────────────── */

function SuccessBanner({ count, label }: { count: number; label: string }) {
  return (
    <div className="flex items-center gap-2 px-4 py-2.5 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg">
      <CheckCircle2 size={16} className="text-green-600 dark:text-green-400 shrink-0" />
      <span className="text-sm font-medium text-green-800 dark:text-green-300">
        {count} {label} imported successfully
      </span>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   RiacImportDialog
   ═══════════════════════════════════════════════════════════════════ */

const DEFAULT_PRESELECT = 5;

export function RiacImportDialog({ projectId, onImported }: RiacImportDialogProps) {
  const [state, setState] = useState<DialogState>({ step: "idle" });
  const [activeTab, setActiveTab] = useState<Tab>("risks");
  const [saving, setSaving] = useState(false);
  const [selectedRisks, setSelectedRisks] = useState<Set<number>>(new Set());
  const [selectedChanges, setSelectedChanges] = useState<Set<number>>(new Set());
  const [risksImported, setRisksImported] = useState(false);
  const [risksImportedCount, setRisksImportedCount] = useState(0);
  const [changesImported, setChangesImported] = useState(false);
  const [changesImportedCount, setChangesImportedCount] = useState(0);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dialogOpen = state.step === "preview" || state.step === "error";

  /* ── Open risks sorted by weight ────────────────────────────── */

  const openRisks = useMemo(() => {
    if (state.step !== "preview") return [];
    return state.data.allRisks
      .filter((r) => !r.status.toLowerCase().includes("close"))
      .sort((a, b) => b.weight - a.weight);
  }, [state]);

  /* ── Actions grouped by risk number ─────────────────────────── */

  const actionsByRisk = useMemo(() => {
    if (state.step !== "preview") return new Map<number, ParsedAction[]>();
    const map = new Map<number, ParsedAction[]>();
    for (const a of state.data.allActions) {
      const list = map.get(a.riskNum) ?? [];
      list.push(a);
      map.set(a.riskNum, list);
    }
    return map;
  }, [state]);

  /* ── Derived counts ─────────────────────────────────────────── */

  const totalSelectedActions = useMemo(() => {
    let count = 0;
    for (const num of selectedRisks) {
      count += (actionsByRisk.get(num) ?? []).length;
    }
    return count;
  }, [selectedRisks, actionsByRisk]);

  const scopeChanges = useMemo(
    () => (state.step === "preview" ? state.data.scopeChanges : []),
    [state],
  );
  const hasChangesInFile = scopeChanges.length > 0;

  /* ── File upload & parse ────────────────────────────────────── */

  const handleFileChange = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setState({ step: "parsing" });
    setRisksImported(false);
    setRisksImportedCount(0);
    setChangesImported(false);
    setChangesImportedCount(0);
    setActiveTab("risks");

    try {
      const formData = new FormData();
      formData.append("file", file);

      const res = await fetch(`/api/projects/${projectId}/risks/import`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setState({ step: "error", message: body.error || "Failed to parse file" });
        return;
      }

      const data: RiacPreview = await res.json();

      // Pre-select top 5 open risks
      const open = data.allRisks
        .filter((r) => !r.status.toLowerCase().includes("close"))
        .sort((a, b) => b.weight - a.weight);
      setSelectedRisks(new Set(open.slice(0, DEFAULT_PRESELECT).map((r) => r.num)));

      // Pre-select all scope changes
      setSelectedChanges(new Set(data.scopeChanges.map((_, i) => i)));

      setState({ step: "preview", data });
    } catch {
      setState({ step: "error", message: "Failed to upload file. Please try again." });
    }

    if (fileInputRef.current) fileInputRef.current.value = "";
  }, [projectId]);

  /* ── Risk selection ─────────────────────────────────────────── */

  const toggleRisk = useCallback((num: number) => {
    setSelectedRisks((prev) => {
      const next = new Set(prev);
      if (next.has(num)) next.delete(num); else next.add(num);
      return next;
    });
  }, []);

  const selectAllRisks = useCallback(() => {
    setSelectedRisks(new Set(openRisks.map((r) => r.num)));
  }, [openRisks]);

  const selectNoRisks = useCallback(() => {
    setSelectedRisks(new Set());
  }, []);

  /* ── Change selection ───────────────────────────────────────── */

  const toggleChange = useCallback((idx: number) => {
    setSelectedChanges((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx); else next.add(idx);
      return next;
    });
  }, []);

  const selectAllChanges = useCallback(() => {
    setSelectedChanges(new Set(scopeChanges.map((_, i) => i)));
  }, [scopeChanges]);

  const selectNoChanges = useCallback(() => {
    setSelectedChanges(new Set());
  }, []);

  /* ── Import risks ───────────────────────────────────────────── */

  const handleImportRisks = useCallback(async () => {
    if (state.step !== "preview") return;
    const { data } = state;

    const finalRisks = data.allRisks.filter((r) => selectedRisks.has(r.num));
    const finalActions = data.allActions.filter((a) => selectedRisks.has(a.riskNum));

    setSaving(true);
    try {
      const res = await fetch(`/api/projects/${projectId}/risks/import`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          risks: finalRisks,
          actions: finalActions,
          summary: data.summary,
        }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setState({ step: "error", message: body.error || "Failed to save risks" });
        return;
      }

      setRisksImported(true);
      setRisksImportedCount(finalRisks.length);
      toast.success(`Imported ${finalRisks.length} risk${finalRisks.length === 1 ? "" : "s"}`, {
        description: finalActions.length > 0 ? `${finalActions.length} action${finalActions.length === 1 ? "" : "s"} attached` : undefined,
      });
      onImported();

      // Auto-navigate to changes tab if changes exist
      if (hasChangesInFile) {
        setActiveTab("changes");
      }
    } catch (err) {
      setState({ step: "error", message: "Failed to save. Please try again." });
      void reportApiError(err, "Risk import failed");
    } finally {
      setSaving(false);
    }
  }, [state, selectedRisks, projectId, onImported, hasChangesInFile]);

  /* ── Import changes ─────────────────────────────────────────── */

  const handleImportChanges = useCallback(async () => {
    if (state.step !== "preview") return;

    const finalChanges = scopeChanges.filter((_, i) => selectedChanges.has(i));

    setSaving(true);
    try {
      const res = await fetch(`/api/projects/${projectId}/risks/import`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scopeChanges: finalChanges }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setState({ step: "error", message: body.error || "Failed to save changes" });
        return;
      }

      setChangesImported(true);
      setChangesImportedCount(finalChanges.length);
      toast.success(`Imported ${finalChanges.length} scope change${finalChanges.length === 1 ? "" : "s"}`);
      onImported();
    } catch (err) {
      setState({ step: "error", message: "Failed to save. Please try again." });
      void reportApiError(err, "Scope change import failed");
    } finally {
      setSaving(false);
    }
  }, [state, scopeChanges, selectedChanges, projectId, onImported]);

  /* ── Close dialog ───────────────────────────────────────────── */

  const handleClose = useCallback(() => {
    setState({ step: "idle" });
    setRisksImported(false);
    setChangesImported(false);
  }, []);

  /* ── Render ─────────────────────────────────────────────────── */

  const preview = state.step === "preview" ? state.data : null;

  return (
    <>
      {/* Trigger button */}
      <button
        onClick={() => fileInputRef.current?.click()}
        disabled={state.step === "parsing"}
        className={cn(
          "inline-flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-semibold rounded transition-colors",
          "bg-etex-orange text-white hover:bg-etex-orange/90 shadow-sm",
          "disabled:opacity-50 disabled:cursor-not-allowed",
        )}
        title="Import risks & scope changes from RIAC Excel"
      >
        {state.step === "parsing" ? (
          <Loader2 size={13} className="animate-spin" />
        ) : (
          <Upload size={13} />
        )}
        Import RIAC
      </button>
      <input
        ref={fileInputRef}
        type="file"
        accept=".xlsx,.xls"
        className="hidden"
        onChange={handleFileChange}
      />

      {/* Dialog */}
      <Dialog open={dialogOpen} onOpenChange={(open) => { if (!open) handleClose(); }}>
        <DialogContent className="max-w-[96vw] w-300 max-h-[92vh] flex flex-col p-0">

          {/* ── Error ────────────────────────────────────────── */}
          {state.step === "error" && (
            <div className="p-6">
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2 text-red-600">
                  <AlertTriangle size={16} />
                  Import Error
                </DialogTitle>
                <DialogDescription>{state.message}</DialogDescription>
              </DialogHeader>
              <DialogFooter className="mt-4">
                <button
                  onClick={handleClose}
                  className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded hover:bg-gray-200 transition-colors"
                >
                  Close
                </button>
              </DialogFooter>
            </div>
          )}

          {/* ── Preview ──────────────────────────────────────── */}
          {preview && (
            <>
              {/* Header */}
              <div className="px-6 pt-5 pb-0 shrink-0">
                <DialogHeader>
                  <DialogTitle className="text-base">Import from RIAC Log</DialogTitle>
                  <DialogDescription className="text-xs">
                    Select what to import from the RIAC file. You can import risks and changes independently.
                  </DialogDescription>
                </DialogHeader>
              </div>

              {/* ── Tab bar — large card-style step tabs ─────────── */}
              <div className="mx-6 mt-4 grid grid-cols-2 gap-3 shrink-0">
                {/* ── Step 1: Risks & Actions ─────────────────────── */}
                <button
                  onClick={() => setActiveTab("risks")}
                  className={cn(
                    "relative flex items-center gap-3 px-4 py-3 rounded-lg border-2 text-left transition-all",
                    activeTab === "risks"
                      ? "border-etex-orange bg-etex-orange/5 dark:bg-etex-orange/10 shadow-sm"
                      : risksImported
                        ? "border-green-300 dark:border-green-700 bg-green-50/50 dark:bg-green-900/10 hover:border-green-400"
                        : "border-gray-200 dark:border-gray-700 bg-gray-50/50 dark:bg-gray-800/30 hover:border-gray-300 dark:hover:border-gray-600",
                  )}
                >
                  {/* Step icon */}
                  <div className={cn(
                    "flex items-center justify-center w-9 h-9 rounded-lg shrink-0 transition-colors",
                    risksImported
                      ? "bg-green-100 dark:bg-green-900/30"
                      : activeTab === "risks"
                        ? "bg-etex-orange/10 dark:bg-etex-orange/20"
                        : "bg-gray-100 dark:bg-gray-800",
                  )}>
                    {risksImported
                      ? <CheckCircle2 size={18} className="text-green-600 dark:text-green-400" />
                      : <ShieldAlert size={18} className={activeTab === "risks" ? "text-etex-orange" : "text-gray-400"} />
                    }
                  </div>

                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className={cn(
                        "text-sm font-semibold leading-tight",
                        activeTab === "risks" ? "text-gray-900 dark:text-gray-100" : "text-gray-600 dark:text-gray-400",
                      )}>
                        Risks & Actions
                      </span>
                      {risksImported && (
                        <span className="text-[9px] font-semibold uppercase tracking-wider text-green-600 dark:text-green-400">
                          Imported
                        </span>
                      )}
                    </div>
                    <div className="text-[11px] text-gray-400 mt-0.5">
                      {risksImported
                        ? `${risksImportedCount} imported`
                        : `${openRisks.length} open risk${openRisks.length !== 1 ? "s" : ""} found`
                      }
                    </div>
                  </div>

                  {/* Count badge */}
                  <span className={cn(
                    "text-xs font-bold px-2 py-1 rounded-md tabular-nums shrink-0",
                    risksImported
                      ? "bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300"
                      : activeTab === "risks"
                        ? "bg-etex-orange/10 text-etex-orange"
                        : "bg-gray-100 dark:bg-gray-800 text-gray-500",
                  )}>
                    {openRisks.length}
                  </span>
                </button>

                {/* ── Step 2: Changes ─────────────────────────────── */}
                <button
                  onClick={() => setActiveTab("changes")}
                  className={cn(
                    "relative flex items-center gap-3 px-4 py-3 rounded-lg border-2 text-left transition-all",
                    activeTab === "changes"
                      ? "border-etex-orange bg-etex-orange/5 dark:bg-etex-orange/10 shadow-sm"
                      : changesImported
                        ? "border-green-300 dark:border-green-700 bg-green-50/50 dark:bg-green-900/10 hover:border-green-400"
                        : !hasChangesInFile
                          ? "border-gray-200 dark:border-gray-700 bg-gray-50/30 dark:bg-gray-800/20 opacity-60"
                          : "border-gray-200 dark:border-gray-700 bg-gray-50/50 dark:bg-gray-800/30 hover:border-gray-300 dark:hover:border-gray-600",
                  )}
                >
                  {/* Step icon */}
                  <div className={cn(
                    "flex items-center justify-center w-9 h-9 rounded-lg shrink-0 transition-colors",
                    changesImported
                      ? "bg-green-100 dark:bg-green-900/30"
                      : activeTab === "changes"
                        ? "bg-etex-orange/10 dark:bg-etex-orange/20"
                        : "bg-gray-100 dark:bg-gray-800",
                  )}>
                    {changesImported
                      ? <CheckCircle2 size={18} className="text-green-600 dark:text-green-400" />
                      : <Repeat size={18} className={activeTab === "changes" ? "text-etex-orange" : "text-gray-400"} />
                    }
                  </div>

                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className={cn(
                        "text-sm font-semibold leading-tight",
                        activeTab === "changes" ? "text-gray-900 dark:text-gray-100" : "text-gray-600 dark:text-gray-400",
                      )}>
                        Scope Changes
                      </span>
                      {changesImported && (
                        <span className="text-[9px] font-semibold uppercase tracking-wider text-green-600 dark:text-green-400">
                          Imported
                        </span>
                      )}
                    </div>
                    <div className="text-[11px] text-gray-400 mt-0.5">
                      {changesImported
                        ? `${changesImportedCount} imported`
                        : hasChangesInFile
                          ? `${scopeChanges.length} change${scopeChanges.length !== 1 ? "s" : ""} found`
                          : "Not found in file"
                      }
                    </div>
                  </div>

                  {/* Count badge */}
                  <span className={cn(
                    "text-xs font-bold px-2 py-1 rounded-md tabular-nums shrink-0",
                    changesImported
                      ? "bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300"
                      : activeTab === "changes"
                        ? "bg-etex-orange/10 text-etex-orange"
                        : "bg-gray-100 dark:bg-gray-800 text-gray-500",
                  )}>
                    {scopeChanges.length}
                  </span>
                </button>
              </div>

              {/* ══════════════════════════════════════════════════
                 RISKS TAB
                 ══════════════════════════════════════════════════ */}
              {activeTab === "risks" && (
                <>
                  {/* Success banner */}
                  {risksImported && (
                    <div className="mx-6 mt-4">
                      <SuccessBanner count={risksImportedCount} label={`risk${risksImportedCount !== 1 ? "s" : ""}`} />
                      {hasChangesInFile && !changesImported && (
                        <button
                          onClick={() => setActiveTab("changes")}
                          className="mt-2 flex items-center gap-1.5 text-sm font-medium text-etex-orange hover:text-etex-orange/80 transition-colors"
                        >
                          <ArrowRight size={14} />
                          Continue to import changes
                        </button>
                      )}
                    </div>
                  )}

                  {/* KPI summary */}
                  {!risksImported && (
                    <>
                      <div className="mx-6 mt-4 grid grid-cols-4 sm:grid-cols-8 gap-px bg-gray-200 dark:bg-gray-700 rounded overflow-hidden shrink-0">
                        <Kpi label="Total" value={preview.summary.totalRisks} />
                        <Kpi label="Open" value={preview.summary.openRisks} color="text-blue-600" />
                        <Kpi label="Issues" value={preview.summary.issues} color={IMPACT_STYLE.ISSUE.text} dot={IMPACT_STYLE.ISSUE.dot} />
                        <Kpi label="High" value={preview.summary.highRisks} color={IMPACT_STYLE.HIGH.text} dot={IMPACT_STYLE.HIGH.dot} />
                        <Kpi label="Moderate" value={preview.summary.moderateRisks} color={IMPACT_STYLE.MODERATE.text} dot={IMPACT_STYLE.MODERATE.dot} />
                        <Kpi label="Low" value={preview.summary.lowRisks} color={IMPACT_STYLE.LOW.text} dot={IMPACT_STYLE.LOW.dot} />
                        <Kpi label="Cost" value={preview.summary.totalCostAtRisk} color="text-red-600" suffix="k€" />
                        <Kpi label="Actions" value={preview.summary.totalActions} />
                      </div>

                      {/* Toolbar */}
                      <div className="flex items-center justify-between mx-6 mt-4 mb-1.5">
                        <div className="text-[11px] font-bold uppercase tracking-wider text-gray-400">
                          Open Risks
                          <span className="text-gray-300 font-normal normal-case ml-1.5">
                            {selectedRisks.size} of {openRisks.length} selected
                          </span>
                        </div>
                        <div className="flex gap-3">
                          <button onClick={selectAllRisks} className="text-[10px] font-medium text-gray-400 hover:text-etex-orange transition-colors">
                            Select all
                          </button>
                          <button onClick={selectNoRisks} className="text-[10px] font-medium text-gray-400 hover:text-etex-orange transition-colors">
                            Clear
                          </button>
                        </div>
                      </div>

                      {/* Risk list */}
                      <div className="flex-1 overflow-y-auto min-h-0 mx-6 mb-2 border border-gray-200 dark:border-gray-700 rounded overflow-hidden">
                        <div
                          className="sticky top-0 z-10 grid items-center gap-2.5 px-3 py-1.5 bg-gray-100 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 text-[9px] font-semibold uppercase tracking-wider text-gray-500"
                          style={{ gridTemplateColumns: "20px minmax(0,1fr) 68px 40px 52px 52px 72px" }}
                        >
                          <span />
                          <span>Description</span>
                          <span className="text-center">Impact</span>
                          <span className="text-center">Wt</span>
                          <span className="text-right">Cost</span>
                          <span className="text-right">Time</span>
                          <span className="text-right">Actions</span>
                        </div>
                        <div className="bg-white dark:bg-[#12121A]">
                          {openRisks.map((risk) => (
                            <RiskCard
                              key={risk.num}
                              risk={risk}
                              actions={actionsByRisk.get(risk.num) ?? []}
                              selected={selectedRisks.has(risk.num)}
                              onToggle={() => toggleRisk(risk.num)}
                            />
                          ))}
                          {openRisks.length === 0 && (
                            <div className="px-4 py-8 text-xs text-gray-400 text-center">
                              No open risks found in the file.
                            </div>
                          )}
                        </div>
                      </div>
                    </>
                  )}

                  {/* Footer */}
                  {!risksImported && (
                    <div className="px-6 py-4 border-t border-gray-100 dark:border-gray-800 flex items-center justify-between gap-4 shrink-0">
                      <p className="text-[11px] text-gray-400">
                        Replaces existing risks. Linked actions become counter-measures.
                      </p>
                      <div className="flex gap-2 shrink-0">
                        {hasChangesInFile && (
                          <button
                            onClick={() => setActiveTab("changes")}
                            className="px-3 py-2 text-[11px] font-medium text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 transition-colors"
                          >
                            Skip to Changes
                          </button>
                        )}
                        <button
                          onClick={handleClose}
                          className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-800 rounded hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
                        >
                          Cancel
                        </button>
                        <button
                          onClick={handleImportRisks}
                          disabled={saving || selectedRisks.size === 0}
                          className={cn(
                            "px-4 py-2 text-sm font-medium text-white rounded transition-colors flex items-center gap-1.5",
                            saving || selectedRisks.size === 0
                              ? "bg-gray-300 dark:bg-gray-600 cursor-not-allowed"
                              : "bg-etex-orange hover:bg-etex-orange/90",
                          )}
                        >
                          {saving && <Loader2 size={13} className="animate-spin" />}
                          Import {selectedRisks.size} Risk{selectedRisks.size !== 1 ? "s" : ""}
                          {totalSelectedActions > 0 && (
                            <span className="text-white/70 font-normal text-xs">+ {totalSelectedActions} action{totalSelectedActions !== 1 ? "s" : ""}</span>
                          )}
                        </button>
                      </div>
                    </div>
                  )}
                </>
              )}

              {/* ══════════════════════════════════════════════════
                 CHANGES TAB
                 ══════════════════════════════════════════════════ */}
              {activeTab === "changes" && (
                <>
                  {/* Success banner for risks if just imported */}
                  {risksImported && !changesImported && (
                    <div className="mx-6 mt-4">
                      <SuccessBanner count={risksImportedCount} label={`risk${risksImportedCount !== 1 ? "s" : ""}`} />
                    </div>
                  )}

                  {/* Changes imported success */}
                  {changesImported && (
                    <div className="mx-6 mt-4">
                      <SuccessBanner count={changesImportedCount} label={`change${changesImportedCount !== 1 ? "s" : ""}`} />
                    </div>
                  )}

                  {!hasChangesInFile ? (
                    /* ── No changes in file ────────────────────────── */
                    <div className="mx-6 mt-6 mb-4 flex flex-col items-center justify-center py-12 text-center">
                      <Repeat size={32} className="text-gray-300 dark:text-gray-600 mb-3" />
                      <p className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-1">No changes found in RIAC file</p>
                      <p className="text-xs text-gray-400">
                        The uploaded file does not contain a &quot;Changes LOG&quot; sheet.
                      </p>
                    </div>
                  ) : !changesImported ? (
                    /* ── Changes list ───────────────────────────────── */
                    <>
                      {/* Prompt text */}
                      {risksImported && (
                        <div className="mx-6 mt-3 text-xs text-gray-500 dark:text-gray-400">
                          The RIAC file also contains <strong>{scopeChanges.length} scope change{scopeChanges.length !== 1 ? "s" : ""}</strong>. Would you like to import them?
                        </div>
                      )}

                      {/* Toolbar */}
                      <div className="flex items-center justify-between mx-6 mt-3 mb-1.5">
                        <div className="text-[11px] font-bold uppercase tracking-wider text-gray-400">
                          Scope Changes
                          <span className="text-gray-300 font-normal normal-case ml-1.5">
                            {selectedChanges.size} of {scopeChanges.length} selected
                          </span>
                        </div>
                        <div className="flex gap-3">
                          <button onClick={selectAllChanges} className="text-[10px] font-medium text-gray-400 hover:text-etex-orange transition-colors">
                            Select all
                          </button>
                          <button onClick={selectNoChanges} className="text-[10px] font-medium text-gray-400 hover:text-etex-orange transition-colors">
                            Clear
                          </button>
                        </div>
                      </div>

                      {/* Changes list */}
                      <div className="flex-1 overflow-y-auto min-h-0 mx-6 mb-2 border border-gray-200 dark:border-gray-700 rounded overflow-hidden">
                        <div
                          className="sticky top-0 z-10 grid items-center gap-2.5 px-3 py-1.5 bg-gray-100 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 text-[9px] font-semibold uppercase tracking-wider text-gray-500"
                          style={{ gridTemplateColumns: "20px 80px minmax(0,2fr) 90px 90px 80px" }}
                        >
                          <span />
                          <span>Date</span>
                          <span>Description</span>
                          <span>Cost</span>
                          <span>Schedule</span>
                          <span className="text-center">Status</span>
                        </div>

                        <div className="bg-white dark:bg-[#12121A]">
                          {scopeChanges.map((sc, i) => (
                            <div
                              key={i}
                              onClick={() => toggleChange(i)}
                              className={cn(
                                "grid items-start gap-2.5 px-3 py-2.5 text-xs border-b border-gray-100 dark:border-gray-800 last:border-0 cursor-pointer transition-colors",
                                selectedChanges.has(i)
                                  ? "bg-etex-orange-50/60 dark:bg-etex-orange/5"
                                  : "hover:bg-gray-50/50 dark:hover:bg-gray-800/30",
                              )}
                              style={{ gridTemplateColumns: "20px 80px minmax(0,2fr) 90px 90px 80px" }}
                            >
                              <div className="pt-0.5"><Tick checked={selectedChanges.has(i)} /></div>
                              <span className="text-gray-500 text-[11px] font-mono tabular-nums">{sc.submittedDate || "—"}</span>
                              <span className="text-gray-800 dark:text-gray-200 leading-snug whitespace-pre-wrap wrap-break-word">{sc.description}</span>
                              <span className="text-gray-500 text-[11px]">{sc.impactCost || "—"}</span>
                              <span className="text-gray-500 text-[11px]">{sc.impactSchedule || "—"}</span>
                              <div className="text-center"><ChangeStatusBadge status={sc.status} /></div>
                            </div>
                          ))}
                        </div>
                      </div>
                    </>
                  ) : null}

                  {/* Footer */}
                  <div className="px-6 py-4 border-t border-gray-100 dark:border-gray-800 flex items-center justify-between gap-4 shrink-0">
                    {!changesImported && hasChangesInFile ? (
                      <>
                        <p className="text-[11px] text-gray-400">
                          Replaces existing scope changes in this project.
                        </p>
                        <div className="flex gap-2 shrink-0">
                          <button
                            onClick={handleClose}
                            className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-800 rounded hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
                          >
                            {risksImported ? "Done" : "Cancel"}
                          </button>
                          <button
                            onClick={handleImportChanges}
                            disabled={saving || selectedChanges.size === 0}
                            className={cn(
                              "px-4 py-2 text-sm font-medium text-white rounded transition-colors flex items-center gap-1.5",
                              saving || selectedChanges.size === 0
                                ? "bg-gray-300 dark:bg-gray-600 cursor-not-allowed"
                                : "bg-etex-orange hover:bg-etex-orange/90",
                            )}
                          >
                            {saving && <Loader2 size={13} className="animate-spin" />}
                            Import {selectedChanges.size} Change{selectedChanges.size !== 1 ? "s" : ""}
                          </button>
                        </div>
                      </>
                    ) : (
                      <>
                        <div />
                        <button
                          onClick={handleClose}
                          className="px-4 py-2 text-sm font-medium text-white bg-etex-orange rounded hover:bg-etex-orange/90 transition-colors"
                        >
                          Done
                        </button>
                      </>
                    )}
                  </div>
                </>
              )}

              {/* ── "All done" footer when both imported on risks tab ── */}
              {activeTab === "risks" && risksImported && (
                <div className="px-6 py-4 border-t border-gray-100 dark:border-gray-800 flex items-center justify-end gap-2 shrink-0">
                  {hasChangesInFile && !changesImported && (
                    <button
                      onClick={() => setActiveTab("changes")}
                      className="px-4 py-2 text-sm font-medium text-etex-orange border border-etex-orange rounded hover:bg-etex-orange/5 transition-colors flex items-center gap-1.5"
                    >
                      <ArrowRight size={14} />
                      Import Changes
                    </button>
                  )}
                  <button
                    onClick={handleClose}
                    className={cn(
                      "px-4 py-2 text-sm font-medium rounded transition-colors",
                      hasChangesInFile && !changesImported
                        ? "text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700"
                        : "text-white bg-etex-orange hover:bg-etex-orange/90",
                    )}
                  >
                    Done
                  </button>
                </div>
              )}
            </>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
