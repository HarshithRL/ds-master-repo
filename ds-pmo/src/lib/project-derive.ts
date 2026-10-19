/**
 * Project derived-field attacher.
 *
 * After centralizing calculations, several values that used to be stored on
 * the Project row are now derived live and added at the API boundary so the
 * rest of the codebase keeps reading them by familiar names:
 *
 *   • progress                 ← computeProgress(gates)
 *   • scheduleBuffer           ← calcScheduleBufferDays(planned, expected)
 *   • scheduleBufferPrev       ← latest snapshot's scheduleBuffer
 *   • totalFloatInclBufferPrev ← latest snapshot's totalFloatInclBuffer
 *   • daysGreenToWhite         ← gates' GREEN→WHITE planned-date span
 *
 * Call once on every project returned from the database. Consumers don't
 * need to change — the field names are preserved.
 */

import { calcScheduleBufferDays } from "@/lib/calculations";
import { computeProgress, computeDaysGreenToWhite } from "@/lib/progress";

type GateLike = {
  gate: string;
  status: string;
  plannedDate: Date | string | null;
  completedDate: Date | string | null;
};

type SnapshotLike = {
  scheduleBuffer: number | null;
  totalFloatInclBuffer: number | null;
};

export type ProjectShape = {
  plannedCompletionDate: Date | string | null;
  expectedCompletionDate: Date | string | null;
  gates?: GateLike[] | null;
  snapshots?: SnapshotLike[] | null;
};

export type DerivedProjectFields = {
  progress: number;
  scheduleBuffer: number | null;
  scheduleBufferPrev: number | null;
  totalFloatInclBufferPrev: number | null;
  daysGreenToWhite: number | null;
};

/**
 * Compute the derived fields for a single project without merging them onto
 * the project object. Useful when callers want the values separately.
 */
export function deriveProjectFields(project: ProjectShape): DerivedProjectFields {
  const latest = project.snapshots?.[0];
  const gates = project.gates ?? [];
  return {
    progress: computeProgress(gates),
    scheduleBuffer: calcScheduleBufferDays(project.plannedCompletionDate, project.expectedCompletionDate),
    scheduleBufferPrev: latest?.scheduleBuffer ?? null,
    totalFloatInclBufferPrev: latest?.totalFloatInclBuffer ?? null,
    daysGreenToWhite: computeDaysGreenToWhite(gates),
  };
}

/**
 * Attach the derived fields onto the project. The returned object is a shallow
 * copy with the four computed properties added (or overwritten if present).
 */
export function withDerivedProjectFields<P extends ProjectShape>(project: P): P & DerivedProjectFields {
  return { ...project, ...deriveProjectFields(project) };
}
