import type { GlobalRole } from "./db/models";

// Client-safe (no src/lib/db/* imports — client components import from here
// for the Permission type and these pure checks). DB-backed access checks
// (canViewProject, canEditProject, visibleProjectsWhere, etc.) live in
// src/lib/access-control.ts instead, kept out of this module specifically so
// importing it never drags @databricks/sql into a client bundle.

export type Permission =
  | "MANAGE_USERS"
  | "MANAGE_FACTORIES"
  | "MANAGE_CATEGORIES"
  | "MANAGE_DIVISIONS"
  | "VIEW_AUDIT_LOGS"
  | "MANAGE_RESOURCES";

export const ALL_PERMISSIONS: Permission[] = [
  "MANAGE_USERS",
  "MANAGE_FACTORIES",
  "MANAGE_CATEGORIES",
  "MANAGE_DIVISIONS",
  "VIEW_AUDIT_LOGS",
  "MANAGE_RESOURCES",
];

export const ALL_GLOBAL_ROLES = ["ADMIN", "EXECUTIVE", "MEMBER"] as const;

// ─── Session-only checks (no DB hit) ──────────────────────────────────────

type SessionUser = {
  id?: string;
  permissions?: string[];
  globalRole?: GlobalRole;
} | null | undefined;

/**
 * Check a single admin-module permission. ADMIN globalRole implicitly
 * holds every permission — they're the superuser, no need to grant
 * each module flag individually.
 */
export function sessionHasPermission(
  sessionUser: SessionUser,
  permission: Permission
): boolean {
  if (sessionUser?.globalRole === "ADMIN") return true;
  if (!sessionUser?.permissions) return false;
  return sessionUser.permissions.includes(permission);
}

/** Drives admin nav visibility — any admin permission OR ADMIN role. */
export function sessionHasAnyPermission(sessionUser: SessionUser): boolean {
  if (sessionUser?.globalRole === "ADMIN") return true;
  return (sessionUser?.permissions?.length ?? 0) > 0;
}

/**
 * True if the user has portfolio-wide read by virtue of their global role.
 *
 * NOTE: this is the *role-only* check. Project-PMO assignment ALSO grants
 * portfolio read but that check requires a DB hit, so it lives in
 * `visibleProjectsWhere()` (for list endpoints) and `canViewProject()` (for
 * detail endpoints) in src/lib/access-control.ts. Don't call this sync
 * helper in places that need the full visibility picture.
 */
export function hasPortfolioRead(sessionUser: SessionUser): boolean {
  const r = sessionUser?.globalRole;
  return r === "ADMIN" || r === "EXECUTIVE";
}

/** True if the user can create/edit/delete any project regardless of attachment. */
export function hasPortfolioEdit(sessionUser: SessionUser): boolean {
  return sessionUser?.globalRole === "ADMIN";
}

// ─── Human-readable denial reasons (surface in 403 responses + UI) ────────

type AccessUser = {
  id: string;
  globalRole?: GlobalRole;
  permissions?: string[];
};

const ROLE_LABEL: Record<GlobalRole, string> = {
  ADMIN: "Administrator",
  EXECUTIVE: "Executive",
  MEMBER: "Member",
};

const PERMISSION_LABEL: Record<Permission, string> = {
  MANAGE_USERS: "Manage Users",
  MANAGE_FACTORIES: "Manage Factories",
  MANAGE_CATEGORIES: "Manage Categories",
  MANAGE_DIVISIONS: "Manage Divisions",
  VIEW_AUDIT_LOGS: "View Audit Logs",
  MANAGE_RESOURCES: "Manage Resources",
};

/** Explain why an admin permission gate refused the request. */
export function whyPermissionDenied(user: AccessUser, permission: Permission): string {
  const role = ROLE_LABEL[user.globalRole ?? "MEMBER"];
  return `This action requires the "${PERMISSION_LABEL[permission]}" admin permission. Your current role is ${role} and that permission has not been granted to your account.`;
}

/** Explain why an admin-only route refused the request. */
export function whyAdminOnly(user: AccessUser): string {
  const role = ROLE_LABEL[user.globalRole ?? "MEMBER"];
  return `This action is restricted to Administrators. Your current role is ${role}.`;
}
