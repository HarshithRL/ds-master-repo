import { selectRows, selectOne, upsertRow, findByIds, insertRows, countRows } from "./query-builder";
import { fromRow, toRow } from "./rowmap";
import type { GateRecord, GateType, GateStatus } from "./models";

const TABLE = "gate_records";

function map(row: Record<string, unknown>): GateRecord {
  return fromRow<GateRecord>(row);
}

export async function listGatesForProject(projectId: string): Promise<GateRecord[]> {
  const rows = await selectRows<Record<string, unknown>>(TABLE, {
    where: [{ type: "eq", column: "project_id", value: projectId }],
  });
  return rows.map(map);
}

export async function listGatesForProjects(projectIds: string[]): Promise<GateRecord[]> {
  return (await findByIds<Record<string, unknown>>(TABLE, "project_id", projectIds)).map(map);
}

export async function getGate(projectId: string, gate: GateType): Promise<GateRecord | null> {
  const row = await selectOne<Record<string, unknown>>(TABLE, {
    where: [
      { type: "eq", column: "project_id", value: projectId },
      { type: "eq", column: "gate", value: gate },
    ],
  });
  return row ? map(row) : null;
}

export async function createDefaultGates(projectId: string, gates: GateType[]): Promise<void> {
  await insertRows(
    TABLE,
    gates.map((gate) => ({
      project_id: projectId,
      gate,
      status: "PLANNED" as GateStatus,
      created_at: new Date(),
      updated_at: new Date(),
    })),
  );
}

export async function countGatesUpdatedBy(userId: string): Promise<number> {
  return countRows(TABLE, [{ type: "eq", column: "updated_by_id", value: userId }]);
}

export interface UpsertGateFields {
  status?: GateStatus;
  plannedDate?: Date | null;
  completedDate?: Date | null;
  notes?: string | null;
  updatedById?: string | null;
}

export async function upsertGate(projectId: string, gate: GateType, fields: UpsertGateFields): Promise<void> {
  const existing = await getGate(projectId, gate);
  await upsertRow(
    TABLE,
    ["project_id", "gate"],
    toRow({
      id: existing?.id,
      projectId,
      gate,
      status: fields.status ?? existing?.status ?? "PLANNED",
      plannedDate: fields.plannedDate !== undefined ? fields.plannedDate : (existing?.plannedDate ?? null),
      completedDate: fields.completedDate !== undefined ? fields.completedDate : (existing?.completedDate ?? null),
      notes: fields.notes !== undefined ? fields.notes : (existing?.notes ?? null),
      updatedById: fields.updatedById !== undefined ? fields.updatedById : (existing?.updatedById ?? null),
      createdAt: existing?.createdAt ?? new Date(),
      updatedAt: new Date(),
    }),
  );
}
