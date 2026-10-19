import { NextResponse } from "next/server";
import { withHandler } from "@/lib/api-handler";
import { listFactories } from "@/lib/db/factories";

export const GET = withHandler({}, async () => {
  const factories = await listFactories(true);
  return NextResponse.json(
    factories.map((f) => ({
      id: f.id,
      name: f.name,
      code: f.code,
      shortName: f.shortName,
      country: f.country,
      currency: f.currency,
      divisionId: f.divisionId,
    })),
  );
});
