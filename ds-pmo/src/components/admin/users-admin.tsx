"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Mail,
  UserPlus,
  Users as UsersIcon,
  Info,
  ShieldCheck,
  Eye,
  UserCog,
  Briefcase,
  X,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { InfoHint } from "@/components/ui/info-hint";
import { PageHeader } from "@/components/layout/page-header";
import { DataTable, type DataTableColumn } from "@/components/ui/data-table";
import { AdminFormDialog } from "@/components/admin/admin-form-dialog";
import {
  LastLoginCell,
  RowActions,
  StatusBadge,
} from "@/components/admin/admin-shared";
import { useAdminResource } from "@/hooks/use-admin-resource";
import { cn } from "@/lib/utils";
import {
  ALL_PERMISSIONS,
  ALL_GLOBAL_ROLES,
  type Permission,
} from "@/lib/permissions";
import type { GlobalRole, User } from "@/lib/db/models";

/* ── Types & constants ─────────────────────────────────────────────── */

type ScopeGrant = { id?: string; divisionId: string | null; factoryId: string | null };

type UserRow = User & {
  lastLoginAt?: Date | string | null;
  scopeGrants?: ScopeGrant[];
};

type UserFormState = {
  email: string;
  name: string;
  isActive: boolean;
  globalRole: GlobalRole;
  permissions: Permission[];
  scopeGrants: ScopeGrant[];
};

const EMPTY_FORM: UserFormState = {
  email: "",
  name: "",
  isActive: true,
  globalRole: "MEMBER",
  permissions: [],
  scopeGrants: [],
};

const PERMISSION_LABELS: Record<Permission, string> = {
  MANAGE_USERS: "Manage Users",
  MANAGE_FACTORIES: "Manage Factories",
  MANAGE_CATEGORIES: "Manage Categories",
  MANAGE_DIVISIONS: "Manage Divisions",
  VIEW_AUDIT_LOGS: "View Audit Logs",
  MANAGE_RESOURCES: "Manage Resources",
};

const PERMISSION_SHORT: Record<Permission, string> = {
  MANAGE_USERS: "USERS",
  MANAGE_FACTORIES: "FACTORIES",
  MANAGE_CATEGORIES: "CATEGORIES",
  MANAGE_DIVISIONS: "DIVISIONS",
  VIEW_AUDIT_LOGS: "AUDIT",
  MANAGE_RESOURCES: "RESOURCES",
};

const ROLE_META: Record<
  GlobalRole,
  { label: string; tone: string; description: string }
> = {
  ADMIN: {
    label: "Administrator",
    tone:
      "bg-red-50 text-red-700 border-red-200 dark:bg-red-500/10 dark:text-red-300 dark:border-red-800",
    description:
      "Full read + edit across the portfolio. Implicitly holds every admin permission.",
  },
  EXECUTIVE: {
    label: "Executive",
    tone:
      "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-500/10 dark:text-blue-300 dark:border-blue-800",
    description:
      "Read-only portfolio access for senior stakeholders (CMO, division heads, chief PMO). Cannot edit.",
  },
  MEMBER: {
    label: "Member",
    tone:
      "bg-gray-50 text-gray-700 border-gray-200 dark:bg-gray-500/10 dark:text-gray-300 dark:border-gray-700",
    description:
      "Default. Sees only projects they're attached to — as PM, PMO, Sponsor, Owner, or via a Scope Grant. Being assigned PMO on any project auto-grants portfolio read.",
  },
};

type ScopeOption = {
  divisions: { id: string; name: string }[];
  factories: { id: string; name: string; divisionName: string | null }[];
};

type ConfirmAction =
  | { type: "deactivate"; user: UserRow }
  | { type: "remove"; user: UserRow };

/* ── User form (body of the AdminFormDialog) ───────────────────────── */

function UserDialog({
  open,
  onOpenChange,
  user,
  onSave,
  error,
  scopeOptions,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  user: UserRow | null;
  onSave: (data: UserFormState) => void;
  error: string | null;
  scopeOptions: ScopeOption | null;
}) {
  const isEdit = !!user;
  // Initialise once on mount — parent remounts via `key` to reset on open/target change.
  const [form, setForm] = useState<UserFormState>(() =>
    user
      ? {
          email: user.email ?? "",
          name: user.name,
          isActive: user.isActive,
          globalRole: (user.globalRole ?? "MEMBER") as GlobalRole,
          permissions: (user.permissions ?? []) as Permission[],
          scopeGrants: (user.scopeGrants ?? []).map((g) => ({
            id: g.id,
            divisionId: g.divisionId,
            factoryId: g.factoryId,
          })),
        }
      : EMPTY_FORM,
  );

  const togglePerm = (perm: Permission) =>
    setForm((p) => ({
      ...p,
      permissions: p.permissions.includes(perm)
        ? p.permissions.filter((x) => x !== perm)
        : [...p.permissions, perm],
    }));

  const addDivisionGrant = (divisionId: string) => {
    if (!divisionId) return;
    if (form.scopeGrants.some((g) => g.divisionId === divisionId)) return;
    setForm((p) => ({
      ...p,
      scopeGrants: [...p.scopeGrants, { divisionId, factoryId: null }],
    }));
  };
  const addFactoryGrant = (factoryId: string) => {
    if (!factoryId) return;
    if (form.scopeGrants.some((g) => g.factoryId === factoryId)) return;
    setForm((p) => ({
      ...p,
      scopeGrants: [...p.scopeGrants, { divisionId: null, factoryId }],
    }));
  };
  const removeGrant = (idx: number) =>
    setForm((p) => ({
      ...p,
      scopeGrants: p.scopeGrants.filter((_, i) => i !== idx),
    }));

  const isAdmin = form.globalRole === "ADMIN";

  return (
    <AdminFormDialog
      open={open}
      onOpenChange={onOpenChange}
      title={isEdit ? `Edit: ${user?.name}` : "Add User"}
      onSubmit={() => onSave(form)}
      submitLabel={isEdit ? "Save Changes" : "Add User"}
      error={error}
      maxWidth="max-w-lg"
    >
      <div className="grid grid-cols-1 gap-3">
        <FieldShell label="Name" hint="Full name as displayed across the platform">
          <Input
            placeholder="Full name"
            value={form.name}
            onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
            className="rounded-sm mt-1 text-sm h-8"
          />
        </FieldShell>
        <FieldShell label="Email" hint="Login email — must be a valid Etex Group address">
          <Input
            type="email"
            placeholder="user@etexgroup.com"
            value={form.email}
            disabled={isEdit}
            onChange={(e) => setForm((p) => ({ ...p, email: e.target.value }))}
            className={cn(
              "rounded-sm mt-1 text-sm h-8",
              isEdit && "bg-muted text-muted-foreground",
            )}
          />
        </FieldShell>
      </div>

      {isEdit && (
        <div className="flex items-center gap-2.5">
          <Switch
            checked={form.isActive}
            onCheckedChange={(v) => setForm((p) => ({ ...p, isActive: v }))}
          />
          <Label className="text-xs cursor-pointer inline-flex items-center gap-1">
            {form.isActive ? "Active" : "Inactive"}
            <InfoHint
              label="Status"
              text="Inactive users cannot sign in or access any projects"
            />
          </Label>
        </div>
      )}

      {/* ── AXIS 1: Global Role ─────────────────────────────────── */}
      <SectionDivider>1. Global Role</SectionDivider>
      <div>
        <p className="text-[11px] text-muted-foreground mb-1.5">
          Posture — what this user sees by default when they log in.
        </p>
        <Select
          value={form.globalRole}
          onValueChange={(v) =>
            setForm((p) => ({ ...p, globalRole: v as GlobalRole }))
          }
        >
          <SelectTrigger className="h-8 text-xs rounded-sm">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {ALL_GLOBAL_ROLES.map((r) => (
              <SelectItem key={r} value={r} className="text-xs">
                {ROLE_META[r].label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p
          className={cn(
            "mt-1.5 rounded-sm border px-2 py-1.5 text-[11px] leading-snug",
            ROLE_META[form.globalRole].tone,
          )}
        >
          {ROLE_META[form.globalRole].description}
        </p>
      </div>

      {/* ── AXIS 2: Admin permissions ───────────────────────────── */}
      <SectionDivider>2. Admin Permissions</SectionDivider>
      <div>
        <p className="text-[11px] text-muted-foreground mb-1.5">
          Access to admin panel sections.{" "}
          {isAdmin
            ? "Administrators implicitly hold all permissions."
            : "Independent from project access."}
        </p>
        <div className={cn("grid grid-cols-2 gap-2", isAdmin && "opacity-60")}>
          {ALL_PERMISSIONS.map((perm) => (
            <label
              key={perm}
              className="flex items-center gap-2 text-xs cursor-pointer select-none"
            >
              <Checkbox
                checked={isAdmin || form.permissions.includes(perm)}
                disabled={isAdmin}
                onCheckedChange={() => togglePerm(perm)}
                className="w-3.5 h-3.5"
              />
              {PERMISSION_LABELS[perm]}
            </label>
          ))}
        </div>
      </div>

      {/* ── AXIS 3: Scope grants ────────────────────────────────── */}
      <SectionDivider>3. Scope Grants (read-only)</SectionDivider>
      <div>
        <p className="text-[11px] text-muted-foreground mb-1.5">
          Grant read access to every project in a Division or Factory. For division
          leaders / regional heads who shouldn&apos;t be hand-attached to each project.
          Edit access still requires a per-project PM/PMO assignment.
        </p>
        {!scopeOptions ? (
          <p className="text-[11px] text-muted-foreground italic">Loading…</p>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-2 mb-2">
              <Select value="" onValueChange={addDivisionGrant}>
                <SelectTrigger className="h-8 text-xs rounded-sm">
                  <SelectValue placeholder="+ Add Division" />
                </SelectTrigger>
                <SelectContent>
                  {scopeOptions.divisions
                    .filter((d) => !form.scopeGrants.some((g) => g.divisionId === d.id))
                    .map((d) => (
                      <SelectItem key={d.id} value={d.id} className="text-xs">
                        {d.name}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>
              <Select value="" onValueChange={addFactoryGrant}>
                <SelectTrigger className="h-8 text-xs rounded-sm">
                  <SelectValue placeholder="+ Add Factory" />
                </SelectTrigger>
                <SelectContent>
                  {scopeOptions.factories
                    .filter((f) => !form.scopeGrants.some((g) => g.factoryId === f.id))
                    .map((f) => (
                      <SelectItem key={f.id} value={f.id} className="text-xs">
                        {f.name}
                        {f.divisionName ? ` — ${f.divisionName}` : ""}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>
            </div>
            {form.scopeGrants.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {form.scopeGrants.map((g, idx) => {
                  const label = g.divisionId
                    ? `Division: ${scopeOptions.divisions.find((d) => d.id === g.divisionId)?.name ?? "?"}`
                    : `Factory: ${scopeOptions.factories.find((f) => f.id === g.factoryId)?.name ?? "?"}`;
                  return (
                    <Badge
                      key={idx}
                      variant="secondary"
                      className="rounded-sm px-1.5 py-0.5 text-[10px] flex items-center gap-1 bg-blue-50 text-blue-700 border border-blue-200 dark:bg-blue-500/15 dark:border-blue-800 dark:text-blue-300"
                    >
                      {label}
                      <button
                        type="button"
                        onClick={() => removeGrant(idx)}
                        className="hover:bg-blue-100 dark:hover:bg-blue-500/30 rounded-sm"
                        aria-label="Remove"
                      >
                        <X className="w-2.5 h-2.5" />
                      </button>
                    </Badge>
                  );
                })}
              </div>
            )}
          </>
        )}
      </div>
    </AdminFormDialog>
  );
}

function SectionDivider({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2 pt-2">
      <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        {children}
      </span>
      <div className="flex-1 h-px bg-border" />
    </div>
  );
}

/* ── Access-model explainer card (shown above the table) ──────────── */

function AccessModelCard() {
  return (
    <div className="rounded-md border border-blue-200 dark:border-blue-900/40 bg-blue-50/40 dark:bg-blue-500/5 p-4 mb-4">
      <div className="flex items-start gap-3">
        <Info className="w-4 h-4 text-blue-600 dark:text-blue-400 shrink-0 mt-0.5" />
        <div className="space-y-2 text-xs leading-relaxed w-full">
          <p className="font-semibold text-gray-900 dark:text-gray-100 text-sm">
            How access works
          </p>
          <p className="text-gray-600 dark:text-gray-400">
            Access is the union of three independent layers — a user can hold any
            combination. Editing on a project requires <strong>only one</strong> of:
            the ADMIN role, or being assigned PM/PMO on that specific project.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-1">
            <AxisCard
              icon={<UserCog className="w-3.5 h-3.5" />}
              title="1. Global Role"
              body="Posture — what they see by default. Only ADMIN grants edit across the portfolio. Being PMO on any project auto-grants portfolio read — no separate role needed."
            />
            <AxisCard
              icon={<ShieldCheck className="w-3.5 h-3.5" />}
              title="2. Admin Permissions"
              body="Module-level flags for the admin panel (Users, Factories…). Independent from project access."
            />
            <AxisCard
              icon={<Eye className="w-3.5 h-3.5" />}
              title="3. Scope Grants"
              body="Read-only bulk access to a Division or Factory's projects. For division/regional leaders."
            />
          </div>
          <p className="text-gray-500 dark:text-gray-500 pt-1 inline-flex items-center gap-1.5">
            <Briefcase className="w-3.5 h-3.5 shrink-0" />
            <span>
              Per-project <strong>PM / PMO assignments</strong> and the Sponsor /
              Owner fields are set inside each project&apos;s detail page — not here.
            </span>
          </p>
        </div>
      </div>
    </div>
  );
}

function AxisCard({
  icon,
  title,
  body,
}: {
  icon: React.ReactNode;
  title: string;
  body: string;
}) {
  return (
    <div className="rounded-sm bg-white dark:bg-[#21252B] border border-blue-100 dark:border-blue-900/40 p-2.5">
      <div className="flex items-center gap-1.5 font-semibold text-gray-800 dark:text-gray-200 mb-1">
        {icon}
        {title}
      </div>
      <p className="text-gray-600 dark:text-gray-400 text-[11px] leading-snug">
        {body}
      </p>
    </div>
  );
}

function FieldShell({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <Label className="text-xs font-medium inline-flex items-center gap-1">
        {label}
        {hint && <InfoHint label={label} text={hint} />}
      </Label>
      {children}
    </div>
  );
}

/* ── Main component ────────────────────────────────────────────────── */

export function UsersAdmin() {
  const { rows: users, loading, error, setError, add, update, remove } =
    useAdminResource<UserRow>({ endpoint: "/api/admin/users", invalidatesReferenceData: false });

  const [search, setSearch] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<UserRow | null>(null);
  const [confirmAction, setConfirmAction] = useState<ConfirmAction | null>(null);
  const [scopeOptions, setScopeOptions] = useState<ScopeOption | null>(null);

  useEffect(() => {
    fetch("/api/admin/users/scope-options")
      .then((r) => (r.ok ? r.json() : null))
      .then((data: ScopeOption | null) => data && setScopeOptions(data))
      .catch(() => {
        /* non-fatal — picker shows "Loading…" */
      });
  }, []);

  /* ── Filter ── */
  const filtered = search
    ? users.filter((u) => {
        const q = search.toLowerCase();
        return (
          u.name.toLowerCase().includes(q) ||
          (u.email?.toLowerCase().includes(q) ?? false)
        );
      })
    : users;

  /* ── Columns ── */
  const columns: DataTableColumn<UserRow>[] = [
    {
      key: "name",
      header: "Name",
      sortable: true,
      sortValue: (r) => r.name,
      render: (u) => (
        <Link
          href={`/admin/users/${u.id}`}
          onClick={(e) => e.stopPropagation()}
          className="flex items-center gap-2 min-w-0 group"
        >
          <div className="w-7 h-7 shrink-0 rounded-full bg-etex-orange/10 text-etex-orange flex items-center justify-center text-[11px] font-semibold border border-etex-orange/20">
            {(u.name || "?").slice(0, 1).toUpperCase()}
          </div>
          <span className="font-medium text-foreground truncate group-hover:text-etex-orange transition-colors">
            {u.name}
          </span>
        </Link>
      ),
    },
    {
      key: "email",
      header: "Email",
      sortable: true,
      sortValue: (r) => r.email ?? "",
      render: (u) =>
        u.email ? (
          <a
            href={`mailto:${u.email}`}
            onClick={(e) => e.stopPropagation()}
            className="inline-flex items-center gap-1.5 text-muted-foreground hover:text-etex-orange transition-colors"
          >
            <Mail className="w-3 h-3 shrink-0" />
            <span className="truncate">{u.email}</span>
          </a>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
      hideBelowSm: true,
    },
    {
      key: "globalRole",
      header: "Role",
      sortable: true,
      sortValue: (r) => (r.globalRole ?? "MEMBER") as string,
      render: (u) => {
        const role = (u.globalRole ?? "MEMBER") as GlobalRole;
        const meta = ROLE_META[role];
        return (
          <Badge
            variant="secondary"
            className={cn(
              "rounded-sm px-1.5 py-0 text-[10px] font-semibold tracking-wider font-mono border",
              meta.tone,
            )}
          >
            {meta.label}
          </Badge>
        );
      },
      width: "120px",
    },
    {
      key: "permissions",
      header: "Permissions",
      render: (u) => {
        if (u.globalRole === "ADMIN") {
          return (
            <span className="text-[11px] text-muted-foreground italic">
              All (implicit)
            </span>
          );
        }
        const perms = (u.permissions ?? []) as Permission[];
        if (perms.length === 0)
          return <span className="text-xs text-muted-foreground">—</span>;
        return (
          <div className="flex flex-wrap gap-1">
            {perms.map((p) => (
              <Badge
                key={p}
                variant="secondary"
                className="rounded-sm px-1.5 py-0 text-[10px] font-semibold tracking-wider font-mono bg-orange-50 text-etex-orange border border-orange-100 dark:bg-etex-orange/15 dark:border-etex-orange/25"
              >
                {PERMISSION_SHORT[p]}
              </Badge>
            ))}
          </div>
        );
      },
    },
    {
      key: "scopeGrants",
      header: "Scope",
      render: (u) => {
        const grants = u.scopeGrants ?? [];
        if (grants.length === 0)
          return <span className="text-xs text-muted-foreground">—</span>;
        const divs = grants.filter((g) => g.divisionId).length;
        const facs = grants.filter((g) => g.factoryId).length;
        const parts = [
          divs > 0 ? `${divs} div` : null,
          facs > 0 ? `${facs} fac` : null,
        ].filter(Boolean);
        return (
          <span className="text-[11px] text-muted-foreground">{parts.join(" · ")}</span>
        );
      },
      width: "90px",
      hideBelowSm: true,
    },
    {
      key: "lastLoginAt",
      header: "Last Login",
      sortable: true,
      sortValue: (r) => (r.lastLoginAt ? new Date(r.lastLoginAt) : null),
      render: (u) => <LastLoginCell value={u.lastLoginAt ?? null} />,
      width: "150px",
      hideBelowSm: true,
    },
    {
      key: "isActive",
      header: "Status",
      sortable: true,
      sortValue: (r) => (r.isActive ? 1 : 0),
      render: (u) => (
        <StatusBadge
          label={u.isActive ? "Active" : "Inactive"}
          tone={u.isActive ? "success" : "neutral"}
        />
      ),
      width: "110px",
    },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (u) => (
        <RowActions
          onEdit={() => setEditTarget(u)}
          onDeactivate={() => setConfirmAction({ type: "deactivate", user: u })}
          onRemove={() => setConfirmAction({ type: "remove", user: u })}
          isActive={u.isActive}
        />
      ),
      width: "120px",
    },
  ];

  const handleSave = async (form: UserFormState, target: UserRow | null) => {
    const scopeGrants = form.scopeGrants.map((g) => ({
      divisionId: g.divisionId,
      factoryId: g.factoryId,
    }));
    const ok = target
      ? await update(target.id, {
          name: form.name,
          isActive: form.isActive,
          globalRole: form.globalRole,
          permissions: form.permissions,
          scopeGrants,
        })
      : await add({
          email: form.email,
          name: form.name,
          globalRole: form.globalRole,
          permissions: form.permissions,
          scopeGrants,
        });
    if (ok) {
      setEditTarget(null);
      setAddOpen(false);
    }
  };

  const confirmProps = confirmAction
    ? confirmAction.type === "deactivate"
      ? {
          title: "Deactivate user",
          description: `${confirmAction.user.name} will be marked inactive and blocked from signing in. This can be reversed later.`,
          confirmLabel: "Deactivate",
          destructive: false,
          onConfirm: async () => {
            await update(confirmAction.user.id, { isActive: false });
          },
        }
      : {
          title: "Remove user",
          description: `${confirmAction.user.name} will be permanently deleted along with their account and project assignments. This cannot be undone.`,
          confirmLabel: "Remove",
          destructive: true,
          onConfirm: () => remove(confirmAction.user.id),
        }
    : null;

  return (
    <>
      <PageHeader
        title="Users"
        subtitle="Manage accounts, roles, and access"
      >
        <Button
          onClick={() => setAddOpen(true)}
          className="bg-etex-orange hover:bg-etex-orange-dark text-white text-xs h-8 shrink-0"
        >
          <UserPlus className="w-3.5 h-3.5 mr-1.5" />
          Add User
        </Button>
      </PageHeader>

      <AccessModelCard />

      <DataTable
        columns={columns}
        data={filtered}
        rowKey={(u) => u.id}
        loading={loading}
        emptyTitle="No users yet"
        emptyMessage="Add your first user to get started with the platform."
        emptyIcon={<UsersIcon className="w-4 h-4" />}
        toolbar={{
          search: {
            value: search,
            onChange: setSearch,
            placeholder: "Search by name or email...",
          },
        }}
      />

      {addOpen && (
        <UserDialog
          key="user-add"
          open
          onOpenChange={(v) => {
            setAddOpen(v);
            if (!v) setError(null);
          }}
          user={null}
          onSave={(form) => handleSave(form, null)}
          error={error}
          scopeOptions={scopeOptions}
        />
      )}
      {editTarget && (
        <UserDialog
          key={`user-edit-${editTarget.id}`}
          open
          onOpenChange={(v) => {
            if (!v) {
              setEditTarget(null);
              setError(null);
            }
          }}
          user={editTarget}
          onSave={(form) => handleSave(form, editTarget)}
          error={error}
          scopeOptions={scopeOptions}
        />
      )}

      {confirmProps && (
        <ConfirmDialog
          open={!!confirmAction}
          onOpenChange={(v) => !v && setConfirmAction(null)}
          {...confirmProps}
        />
      )}
    </>
  );
}
