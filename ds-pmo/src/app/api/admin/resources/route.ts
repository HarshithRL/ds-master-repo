import { withHandler, createAuditLog } from "@/lib/api-handler";
import { createResourceSchema, type CreateResourceInput } from "@/lib/validations";
import { RATE_LIMITS } from "@/lib/rate-limit";
import { NextResponse } from "next/server";
import { createResource } from "@/lib/db/resources";

export const POST = withHandler<CreateResourceInput>(
  {
    permission: "MANAGE_RESOURCES",
    schema: createResourceSchema,
    rateLimit: RATE_LIMITS.mutation,
  },
  async ({ user, body }) => {
    const resource = await createResource({
      category: body.category,
      title: body.title,
      description: body.description || null,
      href: body.href,
      format: body.format || null,
    });

    await createAuditLog({
      userId: user.id,
      action: "CREATE",
      entity: "Resource",
      entityId: resource.id,
      changes: {
        category: { old: null, new: resource.category },
        title: { old: null, new: resource.title },
        href: { old: null, new: resource.href },
      },
    });

    return NextResponse.json(resource, { status: 201 });
  },
);
