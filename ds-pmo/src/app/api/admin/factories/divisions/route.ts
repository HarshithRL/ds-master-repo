import { withHandler } from "@/lib/api-handler";
import { RATE_LIMITS } from "@/lib/rate-limit";
import { NextResponse } from "next/server";
import { listDivisions } from "@/lib/db/divisions";

/**
 * {id, name} list of active divisions — for the division picker on the
 * factory create/edit form. Gated by MANAGE_FACTORIES (the same permission
 * that gates the page hosting it) so a Factory Admin doesn't also need
 * MANAGE_DIVISIONS just to assign one.
 */
export const GET = withHandler(
  { permission: "MANAGE_FACTORIES", rateLimit: RATE_LIMITS.read },
  async () => {
    const divisions = await listDivisions(true);
    return NextResponse.json(divisions.map((d) => ({ id: d.id, name: d.name })));
  },
);
