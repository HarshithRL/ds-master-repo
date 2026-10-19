import { withHandler, createAuditLog } from "@/lib/api-handler";
import { updateGateSchema, type UpdateGateInput } from "@/lib/validations";
import { RATE_LIMITS } from "@/lib/rate-limit";
import { getGate, upsertGate, listGatesForProject } from "@/lib/db/gates";
import { updateProjectRow } from "@/lib/db/projects";
import { GATE_KEYS } from "@/lib/constants";
import { NextResponse } from "next/server";

/**
 * `currentGate` = the furthest-advanced gate that's currently PASSED, per
 * GATE_KEYS' canonical PLC order (RED..WHITE) — not just "whichever gate was
 * last touched". Marking an earlier gate PASSED after a later one is already
 * passed must leave currentGate at the later (already-furthest) gate;
 * un-marking the furthest-passed gate must fall back to whichever passed
 * gate is now furthest. Recomputed from scratch on every gate change so both
 * directions (pass / un-pass) self-correct instead of being special-cased.
 */
async function recomputeCurrentGate(projectId: string): Promise<string | null> {
  const gates = await listGatesForProject(projectId);
  const passed = new Set(gates.filter((g) => g.status === "PASSED").map((g) => g.gate));
  let latest: string | null = null;
  for (const key of GATE_KEYS) {
    if (passed.has(key)) latest = key;
  }
  return latest;
}

export const PUT = withHandler<UpdateGateInput, { id: string }>(
  {
    projectAccess: true,
    schema: updateGateSchema,
    rateLimit: RATE_LIMITS.mutation,
  },
  async ({ user, params, body }) => {
    const gateRecord = await getGate(params.id, body.gate);

    // Shared field translation — applied to both create and update branches
    // of the upsert so a row that doesn't exist yet (e.g. imported project)
    // gets created cleanly on first touch.
    const fieldData: { status: typeof body.status; updatedById: string; completedDate?: Date; notes?: string | null; plannedDate?: Date | null } = {
      status: body.status,
      updatedById: user.id,
    };
    if (body.completedDate) fieldData.completedDate = new Date(body.completedDate);
    if (body.notes !== undefined) fieldData.notes = body.notes;
    if (body.plannedDate !== undefined)
      fieldData.plannedDate = body.plannedDate ? new Date(body.plannedDate) : null;

    await upsertGate(params.id, body.gate, fieldData);
    const updated = await getGate(params.id, body.gate);

    // Recompute unconditionally — covers both marking a (possibly earlier)
    // gate PASSED and un-marking the furthest-passed one.
    const currentGate = await recomputeCurrentGate(params.id);
    await updateProjectRow(params.id, { currentGate });

    await createAuditLog({
      userId: user.id,
      projectId: params.id,
      action: "GATE_PASSED",
      entity: "GateRecord",
      entityId: updated!.id,
      changes: {
        status: { old: gateRecord?.status ?? null, new: body.status },
        completedDate: {
          old: gateRecord?.completedDate ?? null,
          new: body.completedDate ? new Date(body.completedDate) : null,
        },
        notes: { old: gateRecord?.notes ?? null, new: body.notes },
      },
    });

    return NextResponse.json(updated);
  },
);
