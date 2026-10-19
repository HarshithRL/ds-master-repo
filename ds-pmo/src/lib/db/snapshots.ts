import { selectRows, selectOne, upsertRow, countRows, findByIds } from "./query-builder";
import { fromRow, toRow } from "./rowmap";
import type { ProjectSnapshot } from "./models";

const TABLE = "project_snapshots";

function map(row: Record<string, unknown>): ProjectSnapshot {
  return fromRow<ProjectSnapshot>(row);
}

export async function listSnapshotsForProject(projectId: string): Promise<ProjectSnapshot[]> {
  const rows = await selectRows<Record<string, unknown>>(TABLE, {
    where: [{ type: "eq", column: "project_id", value: projectId }],
    orderBy: [{ column: "period_label", direction: "DESC" }],
  });
  return rows.map(map);
}

export async function getSnapshot(projectId: string, periodLabel: string): Promise<ProjectSnapshot | null> {
  const row = await selectOne<Record<string, unknown>>(TABLE, {
    where: [
      { type: "eq", column: "project_id", value: projectId },
      { type: "eq", column: "period_label", value: periodLabel },
    ],
  });
  return row ? map(row) : null;
}

const LATEST_COLUMNS =
  "id, project_id, period_label, rag_progress, rag_schedule, rag_cost, rag_risk, rag_scope, rag_resources, " +
  "variance_at_completion, total_float_incl_buffer, schedule_buffer";

/** Latest snapshot (by periodLabel) per project, narrow projection — for list/detail views. */
export async function getLatestSnapshotsForProjects(projectIds: string[]): Promise<Map<string, Partial<ProjectSnapshot>>> {
  const rows = await findByIds<Record<string, unknown>>(TABLE, "project_id", projectIds, { columns: LATEST_COLUMNS });
  const byProject = new Map<string, Partial<ProjectSnapshot>>();
  for (const raw of rows) {
    const snap = fromRow<Partial<ProjectSnapshot>>(raw);
    const projectId = (raw.project_id as string) ?? "";
    const current = byProject.get(projectId);
    if (!current || (snap.periodLabel ?? "") > (current.periodLabel ?? "")) {
      byProject.set(projectId, snap);
    }
  }
  return byProject;
}

export async function listSnapshots(opts: {
  search?: string;
  limit?: number;
  offset?: number;
}): Promise<{ snapshots: ProjectSnapshot[]; total: number }> {
  const where = opts.search
    ? [
        {
          type: "or" as const,
          conditions: [
            { type: "ilike" as const, column: "project_reference", value: opts.search },
            { type: "ilike" as const, column: "project_name", value: opts.search },
            { type: "ilike" as const, column: "period_label", value: opts.search },
          ],
        },
      ]
    : [];
  const [rows, total] = await Promise.all([
    selectRows<Record<string, unknown>>(TABLE, {
      where,
      orderBy: [{ column: "created_at", direction: "DESC" }],
      limit: opts.limit,
      offset: opts.offset,
    }),
    countRows(TABLE, where),
  ]);
  return { snapshots: rows.map(map), total };
}

export async function countSnapshots(search?: string): Promise<number> {
  const where = search
    ? [
        {
          type: "or" as const,
          conditions: [
            { type: "ilike" as const, column: "project_reference", value: search },
            { type: "ilike" as const, column: "project_name", value: search },
            { type: "ilike" as const, column: "period_label", value: search },
          ],
        },
      ]
    : [];
  return countRows(TABLE, where);
}

export type SnapshotInput = Omit<ProjectSnapshot, "id" | "createdAt">;

export async function countSnapshotsCreatedBy(userId: string): Promise<number> {
  return countRows(TABLE, [{ type: "eq", column: "created_by_id", value: userId }]);
}

export async function upsertSnapshot(input: SnapshotInput): Promise<void> {
  const existing = await getSnapshot(input.projectId, input.periodLabel);
  await upsertRow(
    TABLE,
    ["project_id", "period_label"],
    toRow({
      id: existing?.id,
      ...input,
      createdAt: existing?.createdAt ?? new Date(),
    }),
  );
}
