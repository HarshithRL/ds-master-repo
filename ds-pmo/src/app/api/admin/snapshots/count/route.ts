import { withHandler } from "@/lib/api-handler";
import { RATE_LIMITS } from "@/lib/rate-limit";
import { NextResponse } from "next/server";
import { countRows } from "@/lib/db/query-builder";

export const GET = withHandler(
  { requireAdmin: true, rateLimit: RATE_LIMITS.read },
  async ({ req }) => {
    const period = req.nextUrl.searchParams.get("period") || "";

    if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(period)) {
      return NextResponse.json(
        { error: "Invalid period format. Expected YYYY-MM." },
        { status: 400 },
      );
    }

    // Exact-match count on period_label — `countSnapshots`'s `search` param
    // is an ILIKE substring match across several columns, not what's needed here.
    const count = await countRows("project_snapshots", [
      { type: "eq", column: "period_label", value: period },
    ]);

    return NextResponse.json({ count });
  },
);
