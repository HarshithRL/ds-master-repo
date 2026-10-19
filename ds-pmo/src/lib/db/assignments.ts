import { selectRows, selectOne, insertRow, insertRows, deleteRows, findByIds } from "./query-builder";
import type { WhereCondition } from "./query-builder";
import { fromRow } from "./rowmap";
import type { ProjectAssignment, AssignmentRole } from "./models";

const TABLE = "project_assignments";

function mapAssignment(row: Record<string, unknown>): ProjectAssignment {
  return fromRow<ProjectAssignment>(row);
}

export async function findAssignment(where: {
  projectId?: string;
  userId?: string;
  role?: AssignmentRole | AssignmentRole[];
}): Promise<ProjectAssignment | null> {
  const conditions: WhereCondition[] = [];
  if (where.projectId) conditions.push({ type: "eq" as const, column: "project_id", value: where.projectId });
  if (where.userId) conditions.push({ type: "eq" as const, column: "user_id", value: where.userId });
  if (where.role) {
    conditions.push(
      Array.isArray(where.role)
        ? { type: "in" as const, column: "role", values: where.role }
        : { type: "eq" as const, column: "role", value: where.role },
    );
  }
  const row = await selectOne<Record<string, unknown>>(TABLE, { where: conditions });
  return row ? mapAssignment(row) : null;
}

export async function listAssignmentsForProject(projectId: string): Promise<ProjectAssignment[]> {
  const rows = await selectRows<Record<string, unknown>>(TABLE, {
    where: [{ type: "eq", column: "project_id", value: projectId }],
  });
  return rows.map(mapAssignment);
}

export async function listAssignmentsForProjects(projectIds: string[]): Promise<ProjectAssignment[]> {
  const rows = await findByIds<Record<string, unknown>>(TABLE, "project_id", projectIds);
  return rows.map(mapAssignment);
}

export async function listAssignmentsForUser(
  userId: string,
  role?: AssignmentRole | AssignmentRole[],
): Promise<ProjectAssignment[]> {
  const conditions: WhereCondition[] = [{ type: "eq" as const, column: "user_id", value: userId }];
  if (role) {
    conditions.push(
      Array.isArray(role)
        ? { type: "in" as const, column: "role", values: role }
        : { type: "eq" as const, column: "role", value: role },
    );
  }
  const rows = await selectRows<Record<string, unknown>>(TABLE, { where: conditions });
  return rows.map(mapAssignment);
}

export async function createAssignment(input: { projectId: string; userId: string; role: AssignmentRole }): Promise<void> {
  await insertRow(TABLE, {
    project_id: input.projectId,
    user_id: input.userId,
    role: input.role,
    created_at: new Date(),
  });
}

export async function replaceAssignmentsForProject(
  projectId: string,
  assignments: { userId: string; role: AssignmentRole }[],
): Promise<void> {
  await deleteRows(TABLE, [{ type: "eq", column: "project_id", value: projectId }]);
  if (assignments.length === 0) return;
  await insertRows(
    TABLE,
    assignments.map((a) => ({
      project_id: projectId,
      user_id: a.userId,
      role: a.role,
      created_at: new Date(),
    })),
  );
}

export async function deleteAssignmentsForUser(userId: string): Promise<void> {
  await deleteRows(TABLE, [{ type: "eq", column: "user_id", value: userId }]);
}

/** Batched `GROUP BY user_id` count — the query-builder has no native GROUP BY, so fetch + reduce in JS. */
export async function countAssignmentsForUsers(userIds: string[]): Promise<Map<string, number>> {
  const rows = await findByIds<{ user_id: string }>(TABLE, "user_id", userIds, { columns: "user_id" });
  const counts = new Map<string, number>();
  for (const r of rows) {
    counts.set(r.user_id, (counts.get(r.user_id) ?? 0) + 1);
  }
  return counts;
}

export async function isPmoMember(userId: string): Promise<boolean> {
  const a = await findAssignment({ userId, role: "PMO" });
  return a !== null;
}
