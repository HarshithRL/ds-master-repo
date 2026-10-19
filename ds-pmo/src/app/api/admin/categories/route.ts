import { withHandler, createAuditLog } from "@/lib/api-handler";
import { createCategorySchema, type CreateCategoryInput } from "@/lib/validations";
import { RATE_LIMITS } from "@/lib/rate-limit";
import { NextResponse } from "next/server";

import { listCategories, getCategoryByCode, countProjectsForCategory, createCategory } from "@/lib/db/categories";

export const dynamic = "force-dynamic";

export const GET = withHandler(
  { rateLimit: RATE_LIMITS.read },
  async () => {
    const categories = await listCategories();
    const withCounts = await Promise.all(
      categories.map(async (c) => ({
        ...c,
        _count: { projects: await countProjectsForCategory(c.id) },
      })),
    );
    return NextResponse.json(withCounts);
  },
);

export const POST = withHandler<CreateCategoryInput>(
  {
    permission: "MANAGE_CATEGORIES",
    schema: createCategorySchema,
    rateLimit: RATE_LIMITS.mutation,
  },
  async ({ user, body }) => {
    const existing = await getCategoryByCode(body.code);
    if (existing) {
      return NextResponse.json(
        { error: "Category with this code already exists" },
        { status: 409 },
      );
    }

    const category = await createCategory({ name: body.name, code: body.code, isActive: true });

    await createAuditLog({
      userId: user.id,
      action: "CREATE",
      entity: "Category",
      entityId: category.id,
      changes: {
        name: { old: null, new: body.name },
        code: { old: null, new: body.code },
      },
    });

    return NextResponse.json({ ...category, _count: { projects: 0 } }, { status: 201 });
  },
);
