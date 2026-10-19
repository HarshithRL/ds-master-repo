import { selectRows, selectOne, countRows, insertRow, updateRow, findByIds, readBackWithRetry } from "./query-builder";
import { qualifiedTable } from "./client";
import type { WhereCondition, OrderBy } from "./query-builder";
import { fromRow, toRow } from "./rowmap";
import { getFactoriesByIds, getFactoryById, getFactoryIdsByNames } from "./factories";
import { getDivisionsByIds } from "./divisions";
import { getCategoriesByIds, getCategoryIdsByNames } from "./categories";
import { getUsersByIds } from "./users";
import { listAssignmentsForProject, listAssignmentsForProjects, listAssignmentsForUser } from "./assignments";
import { getBudgetWithLinesForProject, getBudgetsWithLinesForProjects } from "./budgets";
import { listGatesForProject, listGatesForProjects } from "./gates";
import { listRisksForProject, listRisksNarrowForProjects } from "./risks";
import { listMilestonesForProject } from "./milestones";
import { listPlannedActionsForProject } from "./planned-actions";
import { listScopeChangesForProject, listScopeChangesNarrowForProjects } from "./scope-changes";
import { listDocumentsForProject } from "./documents";
import { listAuditLogsForProject } from "./audit-logs";
import { getLatestSnapshotsForProjects } from "./snapshots";
import type { Project, AssignmentRole, ProjectFlag } from "./models";

const TABLE = "projects";
const JSON_COLUMNS = ["wbsCodes", "flags"];

function mapProject(row: Record<string, unknown>): Project {
  return fromRow<Project>(row, JSON_COLUMNS);
}

// ─── Basic lookups ──────────────────────────────────────────────────────

export async function getProjectRaw(id: string): Promise<Project | null> {
  const row = await selectOne<Record<string, unknown>>(TABLE, { where: [{ type: "eq", column: "id", value: id }] });
  return row ? mapProject(row) : null;
}

export interface ProjectBasic {
  id: string;
  name: string;
  reference: string | null;
  factoryId: string | null;
  divisionId: string | null;
  isConfidential: boolean;
}

/** Minimal projection used by permissions.ts — avoids loading the full ~50-column row. */
export async function getProjectBasic(id: string): Promise<ProjectBasic | null> {
  const row = await selectOne<Record<string, unknown>>(TABLE, {
    where: [{ type: "eq", column: "id", value: id }],
    columns: "id, name, reference, factory_id, is_confidential",
  });
  if (!row) return null;
  const basic = fromRow<{ id: string; name: string; reference: string | null; factoryId: string | null; isConfidential: boolean | null }>(row);
  const factory = basic.factoryId ? await getFactoryById(basic.factoryId) : null;
  return { ...basic, isConfidential: basic.isConfidential ?? false, divisionId: factory?.divisionId ?? null };
}

// ─── Visibility → WHERE compilation ────────────────────────────────────
// `ProjectVisibility` is defined here (not in permissions.ts) to avoid a
// permissions.ts <-> db/projects.ts import cycle; permissions.ts imports it
// from here.

export type ProjectVisibility =
  | { unrestricted: true }
  | { unrestricted: false; userId: string; grantedFactoryIds: string[]; grantedDivisionIds: string[] };

async function visibilityCondition(v: ProjectVisibility): Promise<WhereCondition | null> {
  if (v.unrestricted) return null;

  const [ownAssignments, divisionFactories] = await Promise.all([
    listAssignmentsForUser(v.userId),
    v.grantedDivisionIds.length
      ? selectRows<{ id: string }>("factories", {
          where: [{ type: "in", column: "division_id", values: v.grantedDivisionIds }],
          columns: "id",
        })
      : Promise.resolve([]),
  ]);

  const ownProjectIds = [...new Set(ownAssignments.map((a) => a.projectId))];
  const allFactoryIds = [...new Set([...v.grantedFactoryIds, ...divisionFactories.map((f) => f.id)])];

  const or: WhereCondition[] = [];
  if (ownProjectIds.length) or.push({ type: "in", column: "id", values: ownProjectIds });
  if (allFactoryIds.length) or.push({ type: "in", column: "factory_id", values: allFactoryIds });
  if (or.length === 0) return { type: "raw", sql: "1 = 0" }; // no visible projects at all
  return { type: "or", conditions: or };
}

// ─── Filters ────────────────────────────────────────────────────────────

export interface ProjectFilters {
  includeInactive?: boolean;
  msrOnly?: boolean;
  excomOnly?: boolean;
  search?: string;
  phase?: string[];
  lifecycleType?: string;
  tier?: string[];
  factoryNames?: string[]; // may include the synthetic "Unassigned" key
  divisionNames?: string[];
  categoryNames?: string[];
  pmoUserIds?: string[];
  pmUserIds?: string[];
  ownerUserIds?: string[];
  sponsorUserIds?: string[];
  status?: string[];
  visibility: ProjectVisibility;
  /**
   * "ALL" (ADMIN) or the set of project ids the user may see despite
   * confidentiality (derived from their PROJECT_MANAGER/SPONSOR/PMO
   * assignments — see access-control.ts's confidentialProjectAccess).
   * Independent of `visibility`: a project must pass BOTH checks.
   */
  confidentialAccess: "ALL" | string[];
}

async function stakeholderProjectIds(userIds: string[], role: AssignmentRole): Promise<string[]> {
  const rows = await selectRows<{ project_id: string }>("project_assignments", {
    where: [
      { type: "in", column: "user_id", values: userIds },
      { type: "eq", column: "role", value: role },
    ],
    columns: "project_id",
  });
  return [...new Set(rows.map((r) => r.project_id))];
}

function confidentialCondition(access: "ALL" | string[]): WhereCondition | null {
  if (access === "ALL") return null;
  const or: WhereCondition[] = [
    { type: "isNull", column: "is_confidential" },
    { type: "eq", column: "is_confidential", value: false },
  ];
  if (access.length) or.push({ type: "in", column: "id", values: access });
  return { type: "or", conditions: or };
}

async function resolveConditions(f: ProjectFilters): Promise<WhereCondition[]> {
  const conditions: WhereCondition[] = [];
  if (!f.includeInactive) conditions.push({ type: "eq", column: "is_active", value: true });

  if (f.msrOnly) conditions.push({ type: "raw", sql: "flags LIKE ?", params: ["%MSR%"] });
  if (f.excomOnly) conditions.push({ type: "raw", sql: "flags LIKE ?", params: ["%EXCOM_PRESENTING%"] });

  if (f.search) {
    conditions.push({
      type: "or",
      conditions: [
        { type: "ilike", column: "name", value: f.search },
        { type: "ilike", column: "reference", value: f.search },
      ],
    });
  }

  if (f.phase?.length) conditions.push({ type: "in", column: "current_phase", values: f.phase });
  if (f.lifecycleType) conditions.push({ type: "eq", column: "lifecycle_type", value: f.lifecycleType });
  if (f.tier?.length) conditions.push({ type: "in", column: "tier", values: f.tier });
  if (f.status?.length) conditions.push({ type: "in", column: "status", values: f.status });

  if (f.factoryNames?.length) {
    const hasUnassigned = f.factoryNames.some((n) => n.toLowerCase() === "unassigned");
    const names = f.factoryNames.filter((n) => n.toLowerCase() !== "unassigned");
    const ids = names.length ? await getFactoryIdsByNames(names) : [];
    const or: WhereCondition[] = [];
    if (hasUnassigned) or.push({ type: "isNull", column: "factory_id" });
    if (ids.length) or.push({ type: "in", column: "factory_id", values: ids });
    if (or.length) conditions.push(or.length === 1 ? or[0] : { type: "or", conditions: or });
  }

  if (f.divisionNames?.length) {
    const hasUnassigned = f.divisionNames.some((n) => n.toLowerCase() === "unassigned");
    const names = f.divisionNames.filter((n) => n.toLowerCase() !== "unassigned");
    const or: WhereCondition[] = [];
    if (hasUnassigned) or.push({ type: "isNull", column: "factory_id" });
    if (names.length) {
      const divisionIds = (
        await selectRows<{ id: string }>("divisions", {
          where: [{ type: "or", conditions: names.map((n) => ({ type: "ilike" as const, column: "name", value: n })) }],
          columns: "id",
        })
      ).map((r) => r.id);
      const factoryIds = divisionIds.length
        ? (
            await selectRows<{ id: string }>("factories", {
              where: [{ type: "in", column: "division_id", values: divisionIds }],
              columns: "id",
            })
          ).map((r) => r.id)
        : [];
      if (factoryIds.length) or.push({ type: "in", column: "factory_id", values: factoryIds });
    }
    if (or.length) conditions.push(or.length === 1 ? or[0] : { type: "or", conditions: or });
  }

  if (f.categoryNames?.length) {
    const ids = await getCategoryIdsByNames(f.categoryNames);
    conditions.push({ type: "in", column: "category_id", values: ids });
  }

  // Stakeholder filters AND together (project must satisfy all given ones).
  const stakeholderFilters: [string[] | undefined, AssignmentRole][] = [
    [f.sponsorUserIds, "SPONSOR"],
    [f.ownerUserIds, "OWNER"],
    [f.pmUserIds, "PROJECT_MANAGER"],
    [f.pmoUserIds, "PMO"],
  ];
  for (const [ids, role] of stakeholderFilters) {
    if (!ids?.length) continue;
    const matching = await stakeholderProjectIds(ids, role);
    conditions.push({ type: "in", column: "id", values: matching });
  }

  const visCond = await visibilityCondition(f.visibility);
  if (visCond) conditions.push(visCond);

  const confCond = confidentialCondition(f.confidentialAccess);
  if (confCond) conditions.push(confCond);

  return conditions;
}

export interface ListOptions {
  orderBy?: OrderBy[];
  /** Sorting by budget.bac requires a JOIN — pass true to include it. */
  joinBudgetForSort?: boolean;
  limit?: number;
  offset?: number;
}

export async function countProjects(filters: ProjectFilters): Promise<number> {
  return countRows(TABLE, await resolveConditions(filters));
}

/** Bare project rows matching filters — callers attach relations as needed. */
export async function listProjectRows(filters: ProjectFilters, opts: ListOptions = {}): Promise<Project[]> {
  const where = await resolveConditions(filters);
  const table = qualifiedTable(TABLE);
  const joins = opts.joinBudgetForSort ? `LEFT JOIN ${qualifiedTable("budgets")} b ON b.project_id = ${table}.id` : undefined;
  const rows = await selectRows<Record<string, unknown>>(TABLE, {
    where,
    orderBy: opts.orderBy,
    limit: opts.limit,
    offset: opts.offset,
    joins,
    columns: joins ? `${table}.*` : undefined,
  });
  return rows.map(mapProject);
}

// ─── Relation attachment (join emulation) ──────────────────────────────

/**
 * Attach the same relation set the old `PROJECT_LIST_INCLUDE` did, batched
 * (one query per relation type, not per row). Returned as loosely-typed
 * plain objects — consumers already treat these as `any`-shaped API response
 * payloads (see project-derive.ts / project-table-metrics.ts), so this
 * mirrors that rather than fighting TS to model 6 attached relations exactly.
 */
export async function attachListRelations(projects: Project[]): Promise<Record<string, unknown>[]> {
  const ids = projects.map((p) => p.id);
  const factoryIds = [...new Set(projects.map((p) => p.factoryId).filter((x): x is string => !!x))];
  const categoryIds = [...new Set(projects.map((p) => p.categoryId).filter((x): x is string => !!x))];

  const [factories, categories, assignments, budgets, gates, risks, scopeChanges, latestSnapshots] = await Promise.all([
    getFactoriesByIds(factoryIds),
    getCategoriesByIds(categoryIds),
    listAssignmentsForProjects(ids),
    getBudgetsWithLinesForProjects(ids),
    listGatesForProjects(ids),
    listRisksNarrowForProjects(ids),
    listScopeChangesNarrowForProjects(ids),
    getLatestSnapshotsForProjects(ids),
  ]);

  const divisions = await getDivisionsByIds([...new Set(factories.map((f) => f.divisionId).filter((x): x is string => !!x))]);
  const divisionsById = new Map(divisions.map((d) => [d.id, d]));
  const factoriesById = new Map(factories.map((f) => [f.id, { ...f, division: f.divisionId ? (divisionsById.get(f.divisionId) ?? null) : null }]));
  const categoriesById = new Map(categories.map((c) => [c.id, c]));

  const userIds = [...new Set(assignments.map((a) => a.userId))];
  const users = await getUsersByIds(userIds);
  const usersById = new Map(users.map((u) => [u.id, u]));

  const assignmentsByProject = new Map<string, unknown[]>();
  for (const a of assignments) {
    const list = assignmentsByProject.get(a.projectId) ?? [];
    list.push({ ...a, user: usersById.get(a.userId) ?? null });
    assignmentsByProject.set(a.projectId, list);
  }
  const gatesByProject = new Map<string, unknown[]>();
  for (const g of gates) {
    const list = gatesByProject.get(g.projectId) ?? [];
    list.push(g);
    gatesByProject.set(g.projectId, list);
  }
  const risksByProject = new Map<string, unknown[]>();
  for (const r of risks) {
    const list = risksByProject.get(r.projectId as string) ?? [];
    list.push(r);
    risksByProject.set(r.projectId as string, list);
  }
  const scopeChangesByProject = new Map<string, unknown[]>();
  for (const s of scopeChanges) {
    const list = scopeChangesByProject.get(s.projectId as string) ?? [];
    list.push(s);
    scopeChangesByProject.set(s.projectId as string, list);
  }

  return projects.map((p) => ({
    ...p,
    factory: p.factoryId ? (factoriesById.get(p.factoryId) ?? null) : null,
    category: p.categoryId ? (categoriesById.get(p.categoryId) ?? null) : null,
    assignments: assignmentsByProject.get(p.id) ?? [],
    budget: budgets.get(p.id) ?? null,
    gates: gatesByProject.get(p.id) ?? [],
    risks: risksByProject.get(p.id) ?? [],
    scopeChanges: scopeChangesByProject.get(p.id) ?? [],
    snapshots: latestSnapshots.has(p.id) ? [latestSnapshots.get(p.id)] : [],
    _count: { risks: (risksByProject.get(p.id) ?? []).length },
  }));
}

// ─── Full detail (project/[id]) ────────────────────────────────────────

export async function getProjectFull(id: string): Promise<Record<string, unknown> | null> {
  const project = await getProjectRaw(id);
  if (!project) return null;

  const [
    factory,
    category,
    lastUpdatedBy,
    assignments,
    budget,
    gates,
    risks,
    milestones,
    scopeChanges,
    plannedActions,
    documents,
    auditLogs,
    latestSnapshot,
  ] = await Promise.all([
    project.factoryId ? getFactoryById(project.factoryId) : null,
    project.categoryId ? getCategoriesByIds([project.categoryId]).then((r) => r[0] ?? null) : null,
    project.lastUpdatedById ? getUsersByIds([project.lastUpdatedById]).then((r) => r[0] ?? null) : null,
    listAssignmentsForProject(id),
    getBudgetWithLinesForProject(id),
    listGatesForProject(id),
    listRisksForProject(id),
    listMilestonesForProject(id),
    listScopeChangesForProject(id),
    listPlannedActionsForProject(id),
    listDocumentsForProject(id),
    listAuditLogsForProject(id, 10),
    getLatestSnapshotsForProjects([id]),
  ]);

  const users = await getUsersByIds([...new Set(assignments.map((a) => a.userId))]);
  const usersById = new Map(users.map((u) => [u.id, u]));
  const assignmentsWithUser = assignments.map((a) => ({ ...a, user: usersById.get(a.userId) ?? null }));

  return {
    ...project,
    factory,
    category,
    lastUpdatedBy,
    assignments: assignmentsWithUser,
    budget,
    gates,
    risks,
    milestones,
    scopeChanges,
    plannedActions,
    documents,
    auditLogs,
    snapshots: latestSnapshot.has(id) ? [latestSnapshot.get(id)] : [],
  };
}

/** Relations used by the soft-delete DELETE response (a subset of getProjectFull). */
export async function getProjectWithDeleteRelations(id: string): Promise<Record<string, unknown> | null> {
  const project = await getProjectRaw(id);
  if (!project) return null;
  const [factory, category, assignments, budget, gates] = await Promise.all([
    project.factoryId ? getFactoryById(project.factoryId) : null,
    project.categoryId ? getCategoriesByIds([project.categoryId]).then((r) => r[0] ?? null) : null,
    listAssignmentsForProject(id),
    getBudgetWithLinesForProject(id),
    listGatesForProject(id),
  ]);
  const users = await getUsersByIds([...new Set(assignments.map((a) => a.userId))]);
  const usersById = new Map(users.map((u) => [u.id, u]));
  return {
    ...project,
    factory,
    category,
    assignments: assignments.map((a) => ({ ...a, user: usersById.get(a.userId) ?? null })),
    budget,
    gates,
  };
}

// ─── Create / update ────────────────────────────────────────────────────

export interface CreateProjectInput {
  reference?: string | null;
  name: string;
  description?: string | null;
  objective?: string | null;
  scope?: string | null;
  factoryId?: string | null;
  categoryId?: string | null;
  tier: Project["tier"];
  lifecycleType: Project["lifecycleType"];
  status: Project["status"];
  plannedCompletionDate?: string | null;
  expectedCompletionDate?: string | null;
  currentPhase: string;
  flags: ProjectFlag[];
  wbsCodes: string[];
  isConfidential?: boolean;
}

export async function createProject(input: CreateProjectInput): Promise<Project> {
  const now = new Date();
  const id = await insertRow(
    TABLE,
    toRow(
      {
        ...input,
        plannedCompletionDate: input.plannedCompletionDate ? new Date(input.plannedCompletionDate) : null,
        expectedCompletionDate: input.expectedCompletionDate ? new Date(input.expectedCompletionDate) : null,
        isActive: true,
        isConfidential: input.isConfidential ?? false,
        createdAt: now,
        updatedAt: now,
      },
      JSON_COLUMNS,
    ),
  );
  return readBackWithRetry(() => getProjectRaw(id), "Failed to read back created project");
}

export async function updateProjectRow(id: string, fields: Record<string, unknown>): Promise<void> {
  await updateRow(TABLE, id, toRow({ ...fields, updatedAt: new Date() }, JSON_COLUMNS));
}

export async function getProjectsByIds(
  ids: string[],
  columns?: string,
): Promise<Partial<Project>[]> {
  return (await findByIds<Record<string, unknown>>(TABLE, "id", ids, { columns })).map((r) => fromRow<Partial<Project>>(r, JSON_COLUMNS));
}
