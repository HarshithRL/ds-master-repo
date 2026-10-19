import { withHandler } from "@/lib/api-handler";
import { RATE_LIMITS } from "@/lib/rate-limit";
import { NextResponse } from "next/server";
import { listDivisions } from "@/lib/db/divisions";
import { listFactoriesWithDivision } from "@/lib/db/factories";

/**
 * Lightweight {id, name} list of divisions + factories — for the scope grant
 * picker in the user admin UI. Gated by MANAGE_USERS (the same permission that
 * gates the page hosting it) so a User Admin doesn't also need MANAGE_DIVISIONS /
 * MANAGE_FACTORIES to grant scope.
 */
export const GET = withHandler(
  { permission: "MANAGE_USERS", rateLimit: RATE_LIMITS.read },
  async () => {
    const [divisions, factories] = await Promise.all([
      listDivisions(true),
      listFactoriesWithDivision(true),
    ]);

    return NextResponse.json({
      divisions: divisions.map((d) => ({ id: d.id, name: d.name })),
      factories: factories.map((f) => ({
        id: f.id,
        name: f.name,
        divisionId: f.division?.id ?? null,
        divisionName: f.division?.name ?? null,
      })),
    });
  },
);
