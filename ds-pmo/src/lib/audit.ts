import { createAuditLogRow } from "./db/audit-logs";

type AuditAction = "CREATE" | "UPDATE" | "DELETE" | "GATE_PASSED" | "RISK_IMPORT" | "SYNC";

export type AuditChanges = Record<string, { old: unknown; new: unknown }>;

export async function createAuditLog(params: {
  userId?: string;
  projectId?: string;
  action: AuditAction;
  entity: string;
  entityId?: string;
  changes?: AuditChanges;
}) {
  return createAuditLogRow({
    userId: params.userId ?? null,
    projectId: params.projectId ?? null,
    action: params.action,
    entity: params.entity,
    entityId: params.entityId ?? null,
    changes: params.changes ?? null,
  });
}

export function diffObjects<T extends Record<string, unknown>>(
  oldObj: T,
  newObj: Partial<T>,
  fieldsToTrack?: (keyof T)[],
): AuditChanges | null {
  const changes: AuditChanges = {};
  const keys = fieldsToTrack ?? (Object.keys(newObj) as (keyof T)[]);

  for (const key of keys) {
    const k = key as string;
    if (k in newObj && oldObj[k] !== newObj[k]) {
      changes[k] = { old: oldObj[k], new: newObj[k] };
    }
  }

  return Object.keys(changes).length > 0 ? changes : null;
}
