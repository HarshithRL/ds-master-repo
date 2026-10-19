import { NextResponse } from "next/server";
import { withHandler } from "@/lib/api-handler";
import { listCategories } from "@/lib/db/categories";

export const GET = withHandler({}, async () => {
  const categories = await listCategories(true);
  return NextResponse.json(categories.map((c) => ({ id: c.id, name: c.name, code: c.code })));
});
