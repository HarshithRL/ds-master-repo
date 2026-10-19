// Server-only, DB-backed access checks. Split out from permissions.ts because
// that file is imported by client components (for the Permission type and
// pure sessionHasPermission-style checks) — pulling src/lib/db/* (and
// therefore @databricks/sql, a Node-only native-addon package) into that
// import graph broke the client bundle. Keep this file free of any "use
// client" component imports.
import type { GlobalRole } from "./db/models";
import { hasPortfolioRead, hasPortfolioEdit } from "./permissions";
import { isPmoMember as dbIsPmoMember, findAssignment, listAssignmentsForUser } from "./db/assignments";
import { listGrantsForUser, findGrantMatchingFactoryOrDivision } from "./db/scope-grants";
import { getProjectBasic, type ProjectVisibility } from "./db/projects";

export type { ProjectVisibility };

type AccessUser = {
  id: string;
  globalRole?: GlobalRole;
  permissions?: string[];
};

/**
 * Has the user got any ProjectAssignment(PMO)? If so, they're part of the
 * PMO function and get portfolio read across every project — even ones
 * they're not directly attached to. One DB hit; callers may cache per-request.
 */
export async function isPmoMember(userId: string): Promise<boolean> {
  return dbIsPmoMember(userId);
}

/**
 * Confidential-project roles: exactly PROJECT_MANAGER, SPONSOR, PMO — the
 * three roles allowed to see a confidential project, per the feature spec.
 * Owner and scope-grant/portfolio-read access do NOT apply to confidential
 * projects, even though they grant visibility on ordinary ones.
 */
const CONFIDENTIAL_ROLES = ["PROJECT_MANAGER", "OWNER", "SPONSOR", "PMO"] as const;

/**
 * "ALL" (ADMIN sees every confidential project) or the set of project ids
 * this user may see despite confidentiality, derived from their
 * PROJECT_MANAGER/SPONSOR/PMO assignments. Feed into ProjectFilters.confidentialAccess
 * for list endpoints; canViewProject does the single-project equivalent inline.
 */
export async function confidentialProjectAccess(user: AccessUser): Promise<"ALL" | string[]> {
  if (hasPortfolioEdit(user)) return "ALL"; // ADMIN only — Executive is NOT included.
  const assignments = await listAssignmentsForUser(user.id, [...CONFIDENTIAL_ROLES]);
  return [...new Set(assignments.map((a) => a.projectId))];
}

/**
 * Can the user *view* this project's one-pager / detail?
 * Wider than edit — includes executives, project-PMOs (portfolio read),
 * anyone with an assignment (sponsor/owner/PM/PMO), and scope grants.
 *
 * Confidential projects are the one exception: only ADMIN or a
 * PROJECT_MANAGER/SPONSOR/PMO assigned to THIS project can see them — the
 * broader rules above (Owner, Executive, scope grants, portfolio-PMO) do
 * not apply, so this is checked first and short-circuits the rest.
 */
export async function canViewProject(user: AccessUser, projectId: string): Promise<boolean> {
  const project = await getProjectBasic(projectId);
  if (!project) return false;

  if (project.isConfidential) {
    if (hasPortfolioEdit(user)) return true;
    const assignment = await findAssignment({ projectId, userId: user.id, role: [...CONFIDENTIAL_ROLES] });
    return assignment !== null;
  }

  if (hasPortfolioRead(user)) return true;
  if (hasPortfolioEdit(user)) return true;

  // PMO membership (derived from project assignments) grants portfolio read.
  if (await isPmoMember(user.id)) return true;

  const [assignment, scopeGrant] = await Promise.all([
    findAssignment({ projectId, userId: user.id }),
    findGrantMatchingFactoryOrDivision(user.id, project.factoryId, project.divisionId),
  ]);

  return Boolean(assignment) || Boolean(scopeGrant);
}

/**
 * Can the user *edit* this project (gates, risks, budget, fields)?
 * Narrower: ADMIN role OR a ProjectAssignment with role PM or PMO.
 * Sponsor/Owner assignments and executives/scope-grants are explicitly read-only.
 */
export async function canEditProject(user: AccessUser, projectId: string): Promise<boolean> {
  if (hasPortfolioEdit(user)) return true;
  const assignment = await findAssignment({ projectId, userId: user.id, role: ["PROJECT_MANAGER", "PMO"] });
  return assignment !== null;
}

const ROLE_LABEL: Record<GlobalRole, string> = {
  ADMIN: "Administrator",
  EXECUTIVE: "Executive",
  MEMBER: "Member",
};

/** Explain why edit is denied — shown to users so they know what to request. */
export async function whyCantEditProject(user: AccessUser, projectId: string): Promise<string> {
  const [project, sponsorAssignment, ownerAssignment] = await Promise.all([
    getProjectBasic(projectId),
    findAssignment({ projectId, userId: user.id, role: "SPONSOR" }),
    findAssignment({ projectId, userId: user.id, role: "OWNER" }),
  ]);
  const label = project ? (project.reference ? `${project.reference} – ${project.name}` : project.name) : "this project";
  const role = ROLE_LABEL[user.globalRole ?? "MEMBER"];

  const relationship: string[] = [];
  if (sponsorAssignment) relationship.push("Sponsor (read-only)");
  if (ownerAssignment) relationship.push("Owner (read-only)");
  if (user.globalRole === "EXECUTIVE") relationship.push("Executive global role (read-only)");

  const why = relationship.length
    ? `You can view ${label} as ${relationship.join(", ")}, but editing requires being a Project Manager or PMO assigned to this project.`
    : `You don't have edit access to ${label}. Your current role is ${role}. To edit, ask an administrator to assign you as Project Manager or PMO on this project (or grant you the Administrator role).`;

  return why;
}

/** Explain why view is denied. */
export async function whyCantViewProject(user: AccessUser, projectId: string): Promise<string> {
  const project = await getProjectBasic(projectId);
  const label = project ? (project.reference ? `${project.reference} – ${project.name}` : project.name) : "this project";
  const role = ROLE_LABEL[user.globalRole ?? "MEMBER"];
  if (project?.isConfidential) {
    return `${label} is marked confidential. Only its Project Manager, Owner, Sponsor, PMO, or an Administrator can view it. Your current role is ${role}.`;
  }
  return `You don't have access to ${label}. Your current role is ${role}. To view, ask an administrator to attach you to this project (as PM, PMO, Sponsor, or Owner), grant you scope access to its Division or Factory, or promote your role to Executive or Administrator.`;
}

// ─── Project visibility scoping for list endpoints ────────────────────────

export async function visibleProjectsWhere(user: AccessUser): Promise<ProjectVisibility> {
  if (hasPortfolioRead(user) || hasPortfolioEdit(user)) return { unrestricted: true };

  // Project-PMOs see the whole portfolio (derived from assignments — no
  // separate globalRole needed). Same rule as canViewProject; kept in sync.
  if (await isPmoMember(user.id)) return { unrestricted: true };

  const grants = await listGrantsForUser(user.id);
  const grantedFactoryIds = grants.map((g) => g.factoryId).filter((x): x is string => !!x);
  const grantedDivisionIds = grants.map((g) => g.divisionId).filter((x): x is string => !!x);

  return { unrestricted: false, userId: user.id, grantedFactoryIds, grantedDivisionIds };
}
