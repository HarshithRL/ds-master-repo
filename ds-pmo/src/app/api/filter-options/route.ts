import { withHandler } from "@/lib/api-handler";
import { RATE_LIMITS } from "@/lib/rate-limit";
import { listDivisions } from "@/lib/db/divisions";
import { listFactoriesWithDivision } from "@/lib/db/factories";
import { listCategories } from "@/lib/db/categories";
import { getUsersByIds } from "@/lib/db/users";
import { selectRows } from "@/lib/db/query-builder";
import type { AssignmentRole } from "@/lib/db/models";
import { NextResponse } from "next/server";

type FactoryRow = {
  name: string;
  country: string | null;
  division: { name: string } | null;
};

function dedupeFactories(
  rows: FactoryRow[],
): { value: string; label: string; division?: string; country?: string }[] {
  const seen = new Map<string, { value: string; label: string; division?: string; country?: string }>();
  for (const f of rows) {
    const div = f.division?.name ?? "";
    const key = `${f.name}::${div}`;
    if (seen.has(key)) continue;
    seen.set(key, {
      value: f.name,
      label: f.name,
      division: f.division?.name,
      country: f.country ?? undefined,
    });
  }
  return [...seen.values()];
}

/**
 * GET /api/filter-options
 *
 * Returns distinct values for every filter dropdown in one lightweight query.
 * No project data is returned — just the unique labels/ids needed to populate
 * selectors. Results are stable regardless of active filters.
 */
export const GET = withHandler(
  { rateLimit: RATE_LIMITS.read },
  async () => {
    const [divisions, factories, categories, assignmentRows] = await Promise.all([
      listDivisions(),
      listFactoriesWithDivision(),
      listCategories(),
      // All four stakeholder roles now live in project_assignments — one
      // query gives us pmos, pms, owners, sponsors.
      selectRows<{ user_id: string; role: AssignmentRole }>("project_assignments", {
        columns: "user_id, role",
      }),
    ]);

    const distinctUserIds = [...new Set(assignmentRows.map((a) => a.user_id))];
    const users = await getUsersByIds(distinctUserIds);
    const usersById = new Map(users.map((u) => [u.id, u]));

    const toPersonList = (
      items: { id: string; name: string; email: string | null }[],
    ) =>
      items
        .map((u) => ({ id: u.id, name: u.name || u.email || "" }))
        .sort((a, b) => a.name.localeCompare(b.name));

    const usersByRole = (role: AssignmentRole) => {
      const seen = new Set<string>();
      const result: { id: string; name: string; email: string | null }[] = [];
      for (const a of assignmentRows) {
        if (a.role !== role || seen.has(a.user_id)) continue;
        const user = usersById.get(a.user_id);
        if (!user) continue;
        seen.add(a.user_id);
        result.push(user);
      }
      return result;
    };

    return NextResponse.json({
      divisions: divisions.map((d) => d.name),
      // Factory names aren't unique in the DB (e.g. multiple legal entities
      // share the same display name "Etex Services (BE)"). The filter URL
      // param matches by name, so collapsing duplicates within the same
      // division produces a single dropdown row with no loss of meaning.
      factories: dedupeFactories(factories),
      categories: categories.map((c) => ({ value: c.name, code: c.code, name: c.name })),
      pmos: toPersonList(usersByRole("PMO")),
      pms: toPersonList(usersByRole("PROJECT_MANAGER")),
      owners: toPersonList(usersByRole("OWNER")),
      sponsors: toPersonList(usersByRole("SPONSOR")),
    });
  },
);
