import { withHandler, createAuditLog } from "@/lib/api-handler";
import { updateResourceSchema, type UpdateResourceInput } from "@/lib/validations";
import { RATE_LIMITS } from "@/lib/rate-limit";
import { NextResponse } from "next/server";
import { getResourceById, updateResource, deleteResource } from "@/lib/db/resources";
import type { Resource } from "@/lib/db/models";

export const PUT = withHandler<UpdateResourceInput, { id: string }>(
  {
    permission: "MANAGE_RESOURCES",
    schema: updateResourceSchema,
    rateLimit: RATE_LIMITS.mutation,
  },
  async ({ user, params, body }) => {
    const target = await getResourceById(params.id);
    if (!target) {
      return NextResponse.json({ error: "Resource not found" }, { status: 404 });
    }

    const data: Partial<Pick<Resource, "category" | "title" | "description" | "href" | "format">> = {};
    const changes: Record<string, { old: unknown; new: unknown }> = {};

    if (body.category !== undefined && body.category !== target.category) {
      data.category = body.category;
      changes.category = { old: target.category, new: body.category };
    }
    if (body.title !== undefined && body.title !== target.title) {
      data.title = body.title;
      changes.title = { old: target.title, new: body.title };
    }
    if (body.description !== undefined && body.description !== target.description) {
      data.description = body.description;
      changes.description = { old: target.description, new: body.description };
    }
    if (body.href !== undefined && body.href !== target.href) {
      data.href = body.href;
      changes.href = { old: target.href, new: body.href };
    }
    if (body.format !== undefined && body.format !== target.format) {
      data.format = body.format;
      changes.format = { old: target.format, new: body.format };
    }

    await updateResource(params.id, data);

    await createAuditLog({
      userId: user.id,
      action: "UPDATE",
      entity: "Resource",
      entityId: params.id,
      changes,
    });

    const updated = await getResourceById(params.id);
    return NextResponse.json(updated);
  },
);

export const DELETE = withHandler<undefined, { id: string }>(
  {
    permission: "MANAGE_RESOURCES",
    rateLimit: RATE_LIMITS.mutation,
  },
  async ({ user, params }) => {
    const target = await getResourceById(params.id);
    if (!target) {
      return NextResponse.json({ error: "Resource not found" }, { status: 404 });
    }

    await deleteResource(params.id);

    await createAuditLog({
      userId: user.id,
      action: "DELETE",
      entity: "Resource",
      entityId: params.id,
      changes: { title: { old: target.title, new: null } },
    });

    return NextResponse.json({ deleted: true });
  },
);
