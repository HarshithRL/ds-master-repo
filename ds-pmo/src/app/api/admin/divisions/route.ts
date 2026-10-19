import { withHandler } from "@/lib/api-handler";
import { RATE_LIMITS } from "@/lib/rate-limit";
import { NextResponse } from "next/server";
import { listDivisions } from "@/lib/db/divisions";
import { countRows } from "@/lib/db/query-builder";

export const GET = withHandler(
  { permission: "MANAGE_DIVISIONS", rateLimit: RATE_LIMITS.read },
  async () => {
    const divisions = await listDivisions();
    const withCounts = await Promise.all(
      divisions.map(async (d) => ({
        ...d,
        _count: { factories: await countRows("factories", [{ type: "eq", column: "division_id", value: d.id }]) },
      })),
    );
    return NextResponse.json(withCounts);
  },
);
