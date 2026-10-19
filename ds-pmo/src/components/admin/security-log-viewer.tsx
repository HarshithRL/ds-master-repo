"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Clock,
  Filter,
  Globe,
  KeyRound,
  LogIn,
  LogOut,
  Monitor,
  RefreshCw,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  UserCheck,
  UserMinus,
  UserPlus,
  UserX,
  type LucideIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import {
  DataTable,
  type DataTableColumn,
} from "@/components/ui/data-table";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { cn, formatDateTime, formatRelativeTime } from "@/lib/utils";

/* ── Types ──────────────────────────────────────────────────────────── */

type AuditLog = {
  id: string;
  userId: string | null;
  projectId: string | null;
  action: string;
  entity: string;
  entityId: string | null;
  changes: Record<string, unknown> | null;
  createdAt: string;
  user: { id: string; name: string; email: string | null } | null;
  project: { id: string; name: string; reference: string } | null;
};

type Category = "all" | "security" | "project" | "admin";

/* ── Constants ──────────────────────────────────────────────────────── */

const PAGE_SIZE = 25;

const CATEGORIES: { value: Category; label: string; icon: LucideIcon }[] = [
  { value: "all", label: "All Events", icon: Activity },
  { value: "security", label: "Security", icon: Shield },
  { value: "project", label: "Project", icon: Monitor },
  { value: "admin", label: "Admin", icon: KeyRound },
];

type ActionStyle = {
  label: string;
  icon: LucideIcon;
  badgeClass: string;
};

const ACTION_CONFIG: Record<string, ActionStyle> = {
  LOGIN_SUCCESS:    { label: "Login",              icon: LogIn,        badgeClass: "bg-green-50 text-green-700 border-green-200 dark:bg-green-500/10 dark:text-green-400 dark:border-green-500/20" },
  LOGIN_FAILED:     { label: "Login Failed",       icon: ShieldAlert,  badgeClass: "bg-red-50 text-red-700 border-red-200 dark:bg-red-500/10 dark:text-red-400 dark:border-red-500/20" },
  LOGOUT:           { label: "Logout",             icon: LogOut,       badgeClass: "bg-gray-50 text-gray-600 border-gray-200 dark:bg-gray-500/10 dark:text-gray-400 dark:border-gray-500/20" },
  PERMISSION_CHANGED:{label: "Permission Changed", icon: KeyRound,     badgeClass: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-500/10 dark:text-amber-400 dark:border-amber-500/20" },
  USER_CREATED:     { label: "User Created",       icon: UserPlus,     badgeClass: "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-500/10 dark:text-blue-400 dark:border-blue-500/20" },
  USER_DEACTIVATED: { label: "User Deactivated",   icon: UserX,        badgeClass: "bg-red-50 text-red-700 border-red-200 dark:bg-red-500/10 dark:text-red-400 dark:border-red-500/20" },
  USER_REACTIVATED: { label: "User Reactivated",   icon: UserCheck,    badgeClass: "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-500/10 dark:text-blue-400 dark:border-blue-500/20" },
  USER_DELETED:     { label: "User Deleted",       icon: UserMinus,    badgeClass: "bg-red-50 text-red-700 border-red-200 dark:bg-red-500/10 dark:text-red-400 dark:border-red-500/20" },
  CREATE:           { label: "Created",            icon: UserPlus,     badgeClass: "bg-green-50 text-green-700 border-green-200 dark:bg-green-500/10 dark:text-green-400 dark:border-green-500/20" },
  UPDATE:           { label: "Updated",            icon: Activity,     badgeClass: "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-500/10 dark:text-blue-400 dark:border-blue-500/20" },
  DELETE:           { label: "Deleted",            icon: UserMinus,    badgeClass: "bg-red-50 text-red-700 border-red-200 dark:bg-red-500/10 dark:text-red-400 dark:border-red-500/20" },
  GATE_PASSED:      { label: "Gate Passed",        icon: ShieldCheck,  badgeClass: "bg-green-50 text-green-700 border-green-200 dark:bg-green-500/10 dark:text-green-400 dark:border-green-500/20" },
  RISK_IMPORT:      { label: "Risk Import",        icon: AlertTriangle,badgeClass: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-500/10 dark:text-amber-400 dark:border-amber-500/20" },
};

const DEFAULT_ACTION: ActionStyle = {
  label: "Event",
  icon: Activity,
  badgeClass:
    "bg-gray-50 text-gray-600 border-gray-200 dark:bg-gray-500/10 dark:text-gray-400 dark:border-gray-500/20",
};

const META_KEYS = ["ipAddress", "userAgent", "email", "reason", "provider"];

function getActionConfig(action: string): ActionStyle {
  return ACTION_CONFIG[action] ?? { ...DEFAULT_ACTION, label: action };
}

function renderChangeSummary(log: AuditLog): string {
  if (!log.changes) return "—";
  const c = log.changes;
  if (c.email) return String(c.email);
  if (c.reason) return String(c.reason);
  if (c.targetUserName) return `Target: ${c.targetUserName}`;
  const fields = Object.keys(c).filter((k) => !META_KEYS.includes(k));
  if (fields.length === 0) return "—";
  return `${fields.length} field${fields.length > 1 ? "s" : ""} changed`;
}

/* ─────────────────────────────────────────────────────────────────────
   Stats strip                                                         */

function StatsStrip({ logs }: { logs: AuditLog[] }) {
  const startOfDay = new Date();
  startOfDay.setHours(0, 0, 0, 0);
  const today = logs.filter((l) => new Date(l.createdAt) >= startOfDay);

  const stats = [
    {
      label: "Logins Today",
      value: today.filter((l) => l.action === "LOGIN_SUCCESS").length,
      icon: LogIn,
      color: "text-green-600 dark:text-green-400",
      bg: "bg-green-50 dark:bg-green-500/10",
    },
    {
      label: "Failed Attempts",
      value: today.filter((l) => l.action === "LOGIN_FAILED").length,
      icon: ShieldAlert,
      color: "text-red-600 dark:text-red-400",
      bg: "bg-red-50 dark:bg-red-500/10",
    },
    {
      label: "Security Events",
      value: today.filter((l) => l.entity === "Auth" || l.entity === "Security").length,
      icon: Shield,
      color: "text-amber-600 dark:text-amber-400",
      bg: "bg-amber-50 dark:bg-amber-500/10",
    },
    {
      label: "Total Events",
      value: today.length,
      icon: Activity,
      color: "text-blue-600 dark:text-blue-400",
      bg: "bg-blue-50 dark:bg-blue-500/10",
    },
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      {stats.map((s) => (
        <div
          key={s.label}
          className="flex items-center gap-3 rounded-lg border border-border bg-card px-4 py-3"
        >
          <div className={cn("p-2 rounded-md", s.bg)}>
            <s.icon className={cn("w-4 h-4", s.color)} />
          </div>
          <div className="min-w-0">
            <div className={cn("text-lg font-bold leading-tight tabular-nums", s.color)}>
              {s.value}
            </div>
            <div className="text-[11px] text-muted-foreground truncate">{s.label}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────
   Expanded detail                                                      */

function ExpandedDetail({ log }: { log: AuditLog }) {
  const changes = log.changes ?? {};
  const ip = changes.ipAddress as string | undefined;
  const ua = changes.userAgent as string | undefined;
  const email = changes.email as string | undefined;
  const reason = changes.reason as string | undefined;
  const provider = changes.provider as string | undefined;

  const fieldChanges = Object.entries(changes).filter(
    ([k]) => !META_KEYS.includes(k),
  );

  return (
    <div className="px-4 py-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 text-xs">
        <div className="space-y-2">
          <DetailHeader>Event Details</DetailHeader>
          <div className="space-y-1.5 text-muted-foreground">
            {email && <DetailRow icon={Globe}>{email}</DetailRow>}
            {provider && <DetailRow icon={KeyRound}>Provider: {provider}</DetailRow>}
            {reason && <DetailRow icon={AlertTriangle}>Reason: {reason}</DetailRow>}
            {log.project && (
              <DetailRow icon={Monitor}>
                Project: {log.project.reference ? `${log.project.reference} — ${log.project.name}` : log.project.name}
              </DetailRow>
            )}
            <DetailRow icon={Clock}>{formatDateTime(log.createdAt)}</DetailRow>
          </div>
        </div>

        {(ip || ua) && (
          <div className="space-y-2">
            <DetailHeader>Network</DetailHeader>
            <div className="space-y-1.5 text-muted-foreground">
              {ip && (
                <DetailRow icon={Globe}>
                  <span className="font-mono">{ip}</span>
                </DetailRow>
              )}
              {ua && (
                <div>
                  <div className="flex items-center gap-2 mb-0.5">
                    <Monitor className="w-3 h-3 shrink-0" />
                    <span>User Agent</span>
                  </div>
                  <div className="font-mono text-[10px] leading-relaxed break-all pl-5 opacity-70">
                    {ua}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {fieldChanges.length > 0 && (
          <div className="space-y-2">
            <DetailHeader>Changes</DetailHeader>
            <div className="space-y-1.5 max-h-32 overflow-y-auto text-muted-foreground">
              {fieldChanges.map(([key, val]) => {
                const isOldNew =
                  typeof val === "object" &&
                  val !== null &&
                  "old" in val &&
                  "new" in val;
                return (
                  <div key={key}>
                    <span className="font-medium text-foreground">{key}:</span>{" "}
                    {isOldNew ? (
                      <>
                        <span className="line-through opacity-50">
                          {JSON.stringify((val as { old: unknown }).old)}
                        </span>{" "}
                        <span className="text-foreground">
                          → {JSON.stringify((val as { new: unknown }).new)}
                        </span>
                      </>
                    ) : (
                      <span>{JSON.stringify(val)}</span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function DetailHeader({ children }: { children: React.ReactNode }) {
  return (
    <div className="font-semibold text-foreground uppercase tracking-wider text-[10px]">
      {children}
    </div>
  );
}

function DetailRow({ icon: Icon, children }: { icon: LucideIcon; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <Icon className="w-3 h-3 shrink-0" />
      <span className="truncate">{children}</span>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────
   Main                                                                 */

export function SecurityLogViewer() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [category, setCategory] = useState<Category>("all");
  const [searchInput, setSearchInput] = useState("");
  const search = useDebouncedValue(searchInput, 300);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [showFilters, setShowFilters] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);
  const [clearing, setClearing] = useState(false);

  // Reset to page 1 whenever any filter changes
  useEffect(() => { setPage(1); }, [search, category, dateFrom, dateTo]);

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        page: String(page),
        limit: String(PAGE_SIZE),
      });
      if (category !== "all") params.set("category", category);
      if (search) params.set("search", search);
      if (dateFrom) params.set("from", dateFrom);
      if (dateTo) params.set("to", dateTo);

      const res = await fetch(`/api/admin/audit-logs?${params}`);
      if (!res.ok) throw new Error("Failed to load audit logs");
      const data = await res.json();
      setLogs(data.logs);
      setTotal(data.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, [page, category, search, dateFrom, dateTo]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  async function handleClearAll() {
    setClearing(true);
    try {
      const res = await fetch("/api/admin/audit-logs", { method: "DELETE" });
      if (!res.ok) throw new Error("Failed to clear logs");
      setConfirmClear(false);
      fetchLogs();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to clear logs");
    } finally {
      setClearing(false);
    }
  }

  /* ── Columns ── */
  const columns: DataTableColumn<AuditLog>[] = [
    {
      key: "_expand",
      header: "",
      width: "36px",
      render: (log) =>
        expandedId === log.id ? (
          <ChevronUp className="w-3.5 h-3.5 text-muted-foreground" />
        ) : (
          <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />
        ),
    },
    {
      key: "createdAt",
      header: "Timestamp",
      width: "120px",
      render: (log) => (
        <span
          title={formatDateTime(log.createdAt)}
          className="font-mono text-[11px] text-muted-foreground whitespace-nowrap"
        >
          {formatRelativeTime(log.createdAt)}
        </span>
      ),
    },
    {
      key: "user",
      header: "User",
      render: (log) => (
        <div className="min-w-0 max-w-35">
          <div className="truncate text-foreground">{log.user?.name ?? "System"}</div>
          {log.user?.email && (
            <div className="text-[10px] text-muted-foreground/70 truncate">
              {log.user.email}
            </div>
          )}
        </div>
      ),
      hideBelowSm: true,
    },
    {
      key: "action",
      header: "Event",
      render: (log) => {
        const cfg = getActionConfig(log.action);
        const Icon = cfg.icon;
        return (
          <Badge
            variant="secondary"
            className={cn(
              "rounded-sm px-2 py-0.5 text-[10px] font-semibold tracking-wider font-mono inline-flex items-center gap-1 border",
              cfg.badgeClass,
            )}
          >
            <Icon className="w-3 h-3" />
            {cfg.label}
          </Badge>
        );
      },
    },
    {
      key: "entity",
      header: "Entity",
      render: (log) => (
        <span className="font-mono text-[11px] text-muted-foreground">{log.entity}</span>
      ),
      hideBelowSm: true,
    },
    {
      key: "summary",
      header: "Summary",
      render: (log) => (
        <span className="text-[11px] text-muted-foreground truncate inline-block max-w-45">
          {renderChangeSummary(log)}
        </span>
      ),
      hideBelowSm: true,
    },
    {
      key: "ip",
      header: "IP",
      render: (log) => (
        <span className="font-mono text-[11px] text-muted-foreground">
          {(log.changes?.ipAddress as string) || "—"}
        </span>
      ),
      hideBelowSm: true,
    },
  ];

  const categoryPills = (
    <div className="flex gap-1 overflow-x-auto pb-0.5">
      {CATEGORIES.map((cat) => {
        const active = category === cat.value;
        return (
          <button
            key={cat.value}
            onClick={() => {
              setCategory(cat.value);
              setExpandedId(null);
            }}
            className={cn(
              "flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium whitespace-nowrap transition-all border",
              active
                ? "bg-etex-orange text-white border-etex-orange shadow-sm"
                : "bg-card text-muted-foreground border-border hover:bg-muted hover:text-foreground",
            )}
          >
            <cat.icon className="w-3 h-3" />
            {cat.label}
          </button>
        );
      })}
    </div>
  );

  const actions = (
    <div className="flex items-center gap-1.5">
      <Button
        variant="outline"
        size="sm"
        onClick={() => setShowFilters((s) => !s)}
        className={cn("h-8 gap-1.5", showFilters && "bg-muted")}
      >
        <Filter className="w-3.5 h-3.5" />
        <span className="hidden sm:inline text-xs">Filters</span>
      </Button>
      <Button variant="outline" size="sm" onClick={fetchLogs} className="h-8 w-8 p-0">
        <RefreshCw className={cn("w-3.5 h-3.5", loading && "animate-spin")} />
      </Button>
      {total > 0 && (
        <Button
          variant="outline"
          size="sm"
          onClick={() => setConfirmClear(true)}
          className="h-8 gap-1.5 text-red-600 hover:text-red-700 hover:bg-red-50 dark:text-red-400 dark:hover:text-red-300 dark:hover:bg-red-500/10 border-red-200 dark:border-red-500/20"
        >
          <Trash2 className="w-3.5 h-3.5" />
          <span className="hidden sm:inline text-xs">Clear</span>
        </Button>
      )}
    </div>
  );

  const extraFilters = showFilters && (
    <div className="flex flex-wrap items-end gap-3 p-3 rounded-md bg-muted/30 border border-border">
      <FilterDate label="From" value={dateFrom} onChange={setDateFrom} />
      <FilterDate label="To" value={dateTo} onChange={setDateTo} />
      {(dateFrom || dateTo || search) && (
        <Button
          variant="ghost"
          size="sm"
          className="h-8 text-xs text-muted-foreground"
          onClick={() => {
            setDateFrom("");
            setDateTo("");
            setSearchInput("");
          }}
        >
          Clear all
        </Button>
      )}
    </div>
  );

  return (
    <div className="space-y-4">
      {!loading && <StatsStrip logs={logs} />}

      {error && (
        <div className="flex items-center gap-2 px-4 py-3 rounded-md bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 text-xs text-red-700 dark:text-red-400">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          {error}
        </div>
      )}

      <DataTable
        columns={columns}
        data={logs}
        rowKey={(l) => l.id}
        loading={loading}
        emptyTitle="No audit logs"
        emptyMessage={
          category !== "all"
            ? `No ${category} events match your filters.`
            : "Events will appear here as they're recorded."
        }
        emptyIcon={<Shield className="w-4 h-4" />}
        manualSort
        onRowClick={(log) =>
          setExpandedId((cur) => (cur === log.id ? null : log.id))
        }
        expandedRowKey={expandedId}
        expandedRowRender={(log) => <ExpandedDetail log={log} />}
        toolbar={{
          leading: categoryPills,
          search: {
            value: searchInput,
            onChange: setSearchInput,
            placeholder: "Search users, events...",
          },
          actions,
          extra: extraFilters,
        }}
        pagination={{
          page,
          pageSize: PAGE_SIZE,
          total,
          onPageChange: setPage,
        }}
      />

      <ConfirmDialog
        open={confirmClear}
        onOpenChange={setConfirmClear}
        title="Clear all audit logs"
        description={`This will permanently delete all ${total} audit log record${total !== 1 ? "s" : ""}. This action cannot be undone.`}
        confirmLabel={clearing ? "Clearing..." : "Clear All"}
        destructive
        onConfirm={handleClearAll}
      />
    </div>
  );
}

function FilterDate({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="space-y-1">
      <label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
        {label}
      </label>
      <Input
        type="date"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-8 text-xs w-36"
      />
    </div>
  );
}
