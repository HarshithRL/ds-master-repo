import { withHandler, createAuditLog } from "@/lib/api-handler";
import { updateFactorySchema, type UpdateFactoryInput } from "@/lib/validations";
import { RATE_LIMITS } from "@/lib/rate-limit";
import { NextResponse } from "next/server";
import { getFactoryById, updateFactory, deleteFactory, countProjectsForFactory, type CreateFactoryInput } from "@/lib/db/factories";
import { getDivisionById } from "@/lib/db/divisions";

export const PUT = withHandler<UpdateFactoryInput, { id: string }>(
  {
    permission: "MANAGE_FACTORIES",
    schema: updateFactorySchema,
    rateLimit: RATE_LIMITS.mutation,
  },
  async ({ user, params, body }) => {
    const target = await getFactoryById(params.id);
    if (!target) {
      return NextResponse.json({ error: "Factory not found" }, { status: 404 });
    }

    const data: Record<string, unknown> = {};
    const changes: Record<string, { old: unknown; new: unknown }> = {};

    for (const field of ["name", "code", "shortName", "country", "currency", "divisionId"] as const) {
      if (body[field] !== undefined && body[field] !== target[field]) {
        data[field] = body[field];
        changes[field] = { old: target[field], new: body[field] };
      }
    }

    await updateFactory(params.id, data as Partial<CreateFactoryInput>);

    await createAuditLog({
      userId: user.id,
      action: "UPDATE",
      entity: "Factory",
      entityId: params.id,
      changes,
    });

    const updated = await getFactoryById(params.id);
    const division = updated?.divisionId ? await getDivisionById(updated.divisionId) : null;
    const projectCount = await countProjectsForFactory(params.id);
    return NextResponse.json({ ...updated, division, _count: { projects: projectCount } });
  },
);

export const DELETE = withHandler<undefined, { id: string }>(
  {
    permission: "MANAGE_FACTORIES",
    rateLimit: RATE_LIMITS.mutation,
  },
  async ({ user, params }) => {
    const target = await getFactoryById(params.id);
    if (!target) {
      return NextResponse.json({ error: "Factory not found" }, { status: 404 });
    }

    const projectCount = await countProjectsForFactory(params.id);
    if (projectCount > 0) {
      return NextResponse.json(
        { error: `Cannot remove factory: ${projectCount} project(s) are assigned to it.` },
        { status: 409 },
      );
    }

    await deleteFactory(params.id);

    await createAuditLog({
      userId: user.id,
      action: "DELETE",
      entity: "Factory",
      entityId: params.id,
      changes: { name: { old: target.name, new: null } },
    });

    return NextResponse.json({ deleted: true });
  },
);
