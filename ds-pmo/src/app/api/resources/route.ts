import { NextResponse } from "next/server";
import { withHandler } from "@/lib/api-handler";
import { listResources } from "@/lib/db/resources";

export const dynamic = "force-dynamic";

/** Read-only for every authenticated user — powers the Resources page. Writes go through /api/admin/resources. */
export const GET = withHandler({}, async () => {
  const resources = await listResources();
  return NextResponse.json(resources);
});
