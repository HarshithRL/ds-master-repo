"use client";

import { useState } from "react";
import Image from "next/image";
import Link from "next/link";
import {
  Activity,
  Briefcase,
  Calendar,
  Camera,
  CheckCircle2,
  ChevronRight,
  CircleUserRound,
  Clock,
  KeyRound,
  Mail,
  Shield,
  ShieldAlert,
  UserCog,
  type LucideIcon,
} from "lucide-react";

import { PageHeader } from "@/components/layout/page-header";
import { StatusBadge } from "@/components/admin/admin-shared";
import {
  cn,
  formatDate,
  formatDateTime,
  formatRelativeTime,
} from "@/lib/utils";

/* ── Types (matches the server query in app/(dashboard)/profile/page.tsx) ── */

type ProfileUser = {
  id: string;
  name: string;
  email: string | null;
  image: string | null;
  permissions: string[];
  globalRole: string;
  isActive: boolean;
  emailVerified: Date | null;
  lastLoginAt: Date | null;
  createdAt: Date;
  updatedAt: Date;
};

type ProjectStub = {
  id: string;
  reference: string | null;
  name: string;
  currentPhase: string;
  isActive: boolean;
};

type AssignmentRow = {
  id: string;
  role: string;
  createdAt: Date;
  project: ProjectStub;
};

type ActivityRow = {
  id: string;
  action: string;
  entity: string;
  entityId: string | null;
  createdAt: Date;
  changes: unknown;
  project: { id: string; reference: string | null; name: string } | null;
};

interface Props {
  user: ProfileUser;
  assignments: AssignmentRow[];
  recentActivity: ActivityRow[];
  counters: { snapshots: number; gates: number };
  /** Header title (defaults to "Profile" for self-view). */
  title?: string;
  /** Header subtitle. */
  subtitle?: string;
  /** Optional action elements rendered on the right of the page header. */
  headerActions?: React.ReactNode;
}

/* ── Constants ──────────────────────────────────────────────────────── */

const PERMISSION_LABELS: Record<string, string> = {
  MANAGE_USERS: "Manage Users",
  MANAGE_FACTORIES: "Manage Factories",
  MANAGE_CATEGORIES: "Manage Categories",
  MANAGE_DIVISIONS: "Manage Divisions",
  VIEW_AUDIT_LOGS: "View Audit Logs",
  MANAGE_RESOURCES: "Manage Resources",
};

const ROLE_META: Record<string, { label: string; tone: "danger" | "warning" | "info" | "neutral"; icon: LucideIcon }> = {
  ADMIN:     { label: "Administrator",  tone: "danger",  icon: ShieldAlert },
  EXECUTIVE: { label: "Executive",      tone: "info",    icon: Shield },
  MEMBER:    { label: "Member",         tone: "neutral", icon: CircleUserRound },
};

const ROLE_DESCRIPTION: Record<string, string> = {
  ADMIN:     "Full read and edit across the portfolio",
  EXECUTIVE: "Portfolio-wide read (dashboards, one-pagers)",
  MEMBER:    "Sees only projects they're attached to (PMO assignment grants portfolio read)",
};

const ASSIGNMENT_LABEL: Record<string, string> = {
  SPONSOR: "Sponsor",
  OWNER: "Owner",
  PROJECT_MANAGER: "Project Manager",
  PMO: "PMO",
};

/* ─────────────────────────────────────────────────────────────────────
   Profile view                                                         */

export function ProfileView({
  user,
  assignments,
  recentActivity,
  counters,
  title = "Profile",
  subtitle = "Your account, access and recent activity",
  headerActions,
}: Props) {
  const initials = (user.name || user.email || "?").charAt(0).toUpperCase();
  const role = ROLE_META[user.globalRole] ?? ROLE_META.MEMBER;
  const RoleIcon = role.icon;
  // Capture "now" once at mount so the value is stable across re-renders.
  const [now] = useState(() => Date.now());
  const memberDays = Math.max(
    1,
    Math.floor((now - new Date(user.createdAt).getTime()) / 86_400_000),
  );

  return (
    <>
      <PageHeader title={title} subtitle={subtitle}>
        {headerActions}
      </PageHeader>

      {/* ── Hero card ── */}
      <section className="relative overflow-hidden rounded-lg border border-border bg-card">
        {/* Gradient accent */}
        <span
          aria-hidden
          className="absolute inset-x-0 top-0 h-px bg-linear-to-r from-transparent via-etex-orange/60 to-transparent"
        />
        <span
          aria-hidden
          className="absolute -top-24 -right-24 w-72 h-72 rounded-full bg-etex-orange/8 blur-3xl pointer-events-none"
        />

        <div className="relative p-5 sm:p-7 flex flex-col sm:flex-row items-start gap-5 sm:gap-7">
          {/* Avatar */}
          <div className="relative shrink-0">
            <div className="w-20 h-20 rounded-md overflow-hidden shadow-md ring-2 ring-etex-orange/15">
              {user.image ? (
                <Image
                  src={user.image}
                  alt={user.name}
                  width={80}
                  height={80}
                  className="w-full h-full object-cover"
                  unoptimized
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center bg-linear-to-br from-etex-orange via-etex-orange to-etex-orange-dark text-white text-3xl font-bold">
                  {initials}
                </div>
              )}
            </div>
            <span
              className={cn(
                "absolute -bottom-1 -right-1 w-5 h-5 rounded-full ring-2 ring-card flex items-center justify-center",
                user.isActive ? "bg-green-500" : "bg-gray-400",
              )}
              title={user.isActive ? "Active" : "Inactive"}
            >
              <CheckCircle2 className="w-3 h-3 text-white" />
            </span>
          </div>

          {/* Identity */}
          <div className="min-w-0 flex-1">
            <h2 className="text-xl font-bold text-foreground tracking-tight">
              {user.name}
            </h2>
            {user.email && (
              <a
                href={`mailto:${user.email}`}
                className="inline-flex items-center gap-1.5 mt-1 text-sm text-muted-foreground hover:text-etex-orange transition-colors"
              >
                <Mail className="w-3.5 h-3.5" />
                {user.email}
              </a>
            )}

            <div className="mt-3 flex flex-wrap items-center gap-2">
              <span
                className={cn(
                  "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-sm text-[11px] font-semibold border",
                  role.tone === "danger" && "bg-red-50 text-red-700 border-red-200 dark:bg-red-500/10 dark:text-red-400 dark:border-red-500/20",
                  role.tone === "warning" && "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-500/10 dark:text-amber-400 dark:border-amber-500/20",
                  role.tone === "info" && "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-500/10 dark:text-blue-400 dark:border-blue-500/20",
                  role.tone === "neutral" && "bg-muted text-muted-foreground border-border",
                )}
                title={ROLE_DESCRIPTION[user.globalRole] ?? ""}
              >
                <RoleIcon className="w-3 h-3" />
                {role.label}
              </span>

              <StatusBadge
                label={user.isActive ? "Active" : "Inactive"}
                tone={user.isActive ? "success" : "neutral"}
              />

              <span className="text-[11px] text-muted-foreground flex items-center gap-1.5">
                <Calendar className="w-3 h-3" />
                Member for {memberDays} day{memberDays !== 1 ? "s" : ""}
              </span>
            </div>
          </div>
        </div>

        {/* KPI strip */}
        <div className="border-t border-border grid grid-cols-2 sm:grid-cols-4 divide-x divide-border">
          <KpiCell
            icon={Clock}
            label="Last sign-in"
            value={user.lastLoginAt ? formatRelativeTime(user.lastLoginAt) : "Never"}
            title={user.lastLoginAt ? formatDateTime(user.lastLoginAt) : ""}
          />
          <KpiCell
            icon={Briefcase}
            label="Assignments"
            value={assignments.length}
          />
          <KpiCell
            icon={Camera}
            label="Snapshots taken"
            value={counters.snapshots}
          />
          <KpiCell
            icon={CheckCircle2}
            label="Gates updated"
            value={counters.gates}
          />
        </div>
      </section>

      {/* ── Two-column body ── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mt-6">
        {/* Left column — Access & details */}
        <div className="lg:col-span-1 space-y-4">
          <Card title="Account" icon={UserCog}>
            <DetailRow label="Full name" value={user.name} />
            <DetailRow label="Email" value={user.email ?? "—"} mono />
            <DetailRow label="User ID" value={user.id} mono small />
            <DetailRow
              label="Email verified"
              value={user.emailVerified ? formatDate(user.emailVerified) : "Not verified"}
            />
            <DetailRow label="Account created" value={formatDate(user.createdAt)} />
            <DetailRow label="Last updated" value={formatDate(user.updatedAt)} />
          </Card>

          <Card title="Role & Permissions" icon={KeyRound}>
            <DetailRow
              label="Global role"
              value={
                <span className="inline-flex items-center gap-1.5">
                  <RoleIcon className="w-3 h-3" />
                  {role.label}
                </span>
              }
            />
            <p className="text-[11px] text-muted-foreground -mt-1 pb-2 leading-relaxed">
              {ROLE_DESCRIPTION[user.globalRole] ?? ""}
            </p>

            <div className="pt-2 border-t border-border">
              <p className="text-[10px] uppercase tracking-wider font-semibold text-muted-foreground mb-2">
                Module permissions
              </p>
              {user.permissions.length === 0 ? (
                <p className="text-xs text-muted-foreground italic">
                  No additional permissions
                </p>
              ) : (
                <div className="flex flex-col gap-1.5">
                  {user.permissions.map((p) => (
                    <div
                      key={p}
                      className="flex items-center gap-2 text-xs"
                    >
                      <CheckCircle2 className="w-3 h-3 text-green-600 dark:text-green-400 shrink-0" />
                      <span>{PERMISSION_LABELS[p] ?? p}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </Card>
        </div>

        {/* Right column — Projects + Activity */}
        <div className="lg:col-span-2 space-y-4">
          <Card title="Project Assignments" icon={Briefcase}>
            {assignments.length === 0 ? (
              <EmptyHint message="You're not assigned to any projects yet." />
            ) : (
              <ul className="divide-y divide-border -mx-4">
                {assignments.map((a) => (
                  <ProjectListItem
                    key={a.id}
                    project={a.project}
                    badge={ASSIGNMENT_LABEL[a.role] ?? a.role}
                    badgeTone="info"
                  />
                ))}
              </ul>
            )}
          </Card>


          <Card title="Recent activity" icon={Activity}>
            {recentActivity.length === 0 ? (
              <EmptyHint message="No recorded activity yet." />
            ) : (
              <ol className="relative space-y-3 pl-4 border-l border-border ml-0.5">
                {recentActivity.map((a) => (
                  <ActivityItem key={a.id} item={a} />
                ))}
              </ol>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}

/* ── Building blocks ─────────────────────────────────────────────────── */

function KpiCell({
  icon: Icon,
  label,
  value,
  title,
}: {
  icon: LucideIcon;
  label: string;
  value: React.ReactNode;
  title?: string;
}) {
  return (
    <div className="px-4 py-3 flex items-center gap-3" title={title}>
      <div className="w-8 h-8 rounded-md bg-etex-orange/10 text-etex-orange flex items-center justify-center">
        <Icon className="w-4 h-4" />
      </div>
      <div className="min-w-0">
        <div className="text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">
          {label}
        </div>
        <div className="text-sm font-bold text-foreground truncate tabular-nums">
          {value}
        </div>
      </div>
    </div>
  );
}

function Card({
  title,
  icon: Icon,
  children,
}: {
  title: string;
  icon: LucideIcon;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-lg border border-border bg-card overflow-hidden">
      <header className="flex items-center gap-2 px-4 py-2.5 border-b border-border bg-muted/30">
        <Icon className="w-3.5 h-3.5 text-etex-orange" />
        <h3 className="text-xs font-semibold uppercase tracking-wider text-foreground">
          {title}
        </h3>
      </header>
      <div className="px-4 py-3 space-y-2">{children}</div>
    </section>
  );
}

function DetailRow({
  label,
  value,
  mono,
  small,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
  small?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 text-xs py-0.5">
      <span className="text-muted-foreground shrink-0">{label}</span>
      <span
        className={cn(
          "text-foreground text-right truncate min-w-0",
          mono && "font-mono",
          small && "text-[11px]",
        )}
      >
        {value}
      </span>
    </div>
  );
}

function ProjectListItem({
  project,
  badge,
  badgeTone = "neutral",
}: {
  project: ProjectStub;
  badge?: string;
  badgeTone?: "info" | "neutral";
}) {
  return (
    <li>
      <Link
        href={`/projects/${project.id}`}
        className="group flex items-center gap-3 px-4 py-2.5 hover:bg-etex-orange/5 transition-colors"
      >
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs text-etex-orange shrink-0">
              {project.reference ?? "—"}
            </span>
            <span className="text-sm text-foreground truncate">{project.name}</span>
          </div>
          <div className="text-[11px] text-muted-foreground mt-0.5">
            {project.currentPhase.replace(/_/g, " ")}
            {!project.isActive && " · archived"}
          </div>
        </div>
        {badge && <StatusBadge label={badge} tone={badgeTone} />}
        <ChevronRight className="w-3.5 h-3.5 text-muted-foreground/50 group-hover:text-etex-orange transition-colors" />
      </Link>
    </li>
  );
}

function ActivityItem({ item }: { item: ActivityRow }) {
  const label = item.action.replace(/_/g, " ").toLowerCase();
  return (
    <li className="relative">
      <span
        aria-hidden
        className="absolute -left-4.25 top-1 w-2 h-2 rounded-full bg-etex-orange ring-2 ring-card"
      />
      <div className="text-xs">
        <span className="font-medium text-foreground capitalize">{label}</span>
        <span className="text-muted-foreground"> · {item.entity}</span>
        {item.project && (
          <Link
            href={`/projects/${item.project.id}`}
            className="text-muted-foreground hover:text-etex-orange ml-1 truncate"
          >
            ({item.project.reference ?? item.project.name})
          </Link>
        )}
      </div>
      <div className="text-[10px] text-muted-foreground/80 font-mono mt-0.5">
        {formatDateTime(item.createdAt)} · {formatRelativeTime(item.createdAt)}
      </div>
    </li>
  );
}

function EmptyHint({ message }: { message: string }) {
  return (
    <p className="text-xs text-muted-foreground italic text-center py-3">
      {message}
    </p>
  );
}
