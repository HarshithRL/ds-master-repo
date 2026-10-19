import { withHandler, createAuditLog } from "@/lib/api-handler";
import { createFactorySchema, type CreateFactoryInput } from "@/lib/validations";
import { RATE_LIMITS } from "@/lib/rate-limit";
import { NextResponse } from "next/server";
import { listFactoriesWithDivision, getFactoryByCode, countProjectsForFactory, createFactory } from "@/lib/db/factories";
import { getDivisionById } from "@/lib/db/divisions";

export const GET = withHandler(
  { permission: "MANAGE_FACTORIES", rateLimit: RATE_LIMITS.read },
  async () => {
    const factories = await listFactoriesWithDivision();
    const withCounts = await Promise.all(
      factories.map(async (f) => ({
        ...f,
        _count: { projects: await countProjectsForFactory(f.id) },
      })),
    );
    return NextResponse.json(withCounts);
  },
);

export const POST = withHandler<CreateFactoryInput>(
  {
    permission: "MANAGE_FACTORIES",
    schema: createFactorySchema,
    rateLimit: RATE_LIMITS.mutation,
  },
  async ({ user, body }) => {
    if (body.code) {
      const existing = await getFactoryByCode(body.code);
      if (existing) {
        return NextResponse.json(
          { error: "Factory with this code already exists" },
          { status: 409 },
        );
      }
    }

    const factory = await createFactory({
      name: body.name,
      code: body.code || null,
      shortName: body.shortName,
      country: body.country,
      currency: body.currency,
      divisionId: body.divisionId,
      isActive: true,
    });

    await createAuditLog({
      userId: user.id,
      action: "CREATE",
      entity: "Factory",
      entityId: factory.id,
      changes: {
        name: { old: null, new: body.name },
        code: { old: null, new: body.code },
        country: { old: null, new: body.country },
      },
    });

    const division = factory.divisionId ? await getDivisionById(factory.divisionId) : null;
    return NextResponse.json({ ...factory, division, _count: { projects: 0 } }, { status: 201 });
  },
);
