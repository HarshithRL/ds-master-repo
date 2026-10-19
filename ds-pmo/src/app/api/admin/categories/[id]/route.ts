import { withHandler, createAuditLog } from "@/lib/api-handler";
import { updateCategorySchema, type UpdateCategoryInput } from "@/lib/validations";
import { RATE_LIMITS } from "@/lib/rate-limit";
import { NextResponse } from "next/server";
import { getCategoryById, updateCategory, deleteCategory, countProjectsForCategory } from "@/lib/db/categories";

export const PUT = withHandler<UpdateCategoryInput, { id: string }>(
  {
    permission: "MANAGE_CATEGORIES",
    schema: updateCategorySchema,
    rateLimit: RATE_LIMITS.mutation,
  },
  async ({ user, params, body }) => {
    const target = await getCategoryById(params.id);
    if (!target) {
      return NextResponse.json({ error: "Category not found" }, { status: 404 });
    }

    const data: Partial<{ name: string }> = {};
    const changes: Record<string, { old: unknown; new: unknown }> = {};

    if (body.name !== undefined && body.name !== target.name) {
      data.name = body.name;
      changes.name = { old: target.name, new: body.name };
    }

    await updateCategory(params.id, data);

    await createAuditLog({
      userId: user.id,
      action: "UPDATE",
      entity: "Category",
      entityId: params.id,
      changes,
    });

    const updated = await getCategoryById(params.id);
    const projectCount = await countProjectsForCategory(params.id);
    return NextResponse.json({ ...updated, _count: { projects: projectCount } });
  },
);

export const DELETE = withHandler<undefined, { id: string }>(
  {
    permission: "MANAGE_CATEGORIES",
    rateLimit: RATE_LIMITS.mutation,
  },
  async ({ user, params }) => {
    const target = await getCategoryById(params.id);
    if (!target) {
      return NextResponse.json({ error: "Category not found" }, { status: 404 });
    }

    const projectCount = await countProjectsForCategory(params.id);
    if (projectCount > 0) {
      return NextResponse.json(
        { error: `Cannot remove category: ${projectCount} project(s) are assigned to it.` },
        { status: 409 },
      );
    }

    await deleteCategory(params.id);

    await createAuditLog({
      userId: user.id,
      action: "DELETE",
      entity: "Category",
      entityId: params.id,
      changes: { name: { old: target.name, new: null } },
    });

    return NextResponse.json({ deleted: true });
  },
);
