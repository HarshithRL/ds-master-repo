import { withHandler, createAuditLog } from "@/lib/api-handler";
import { RATE_LIMITS } from "@/lib/rate-limit";
import { NextResponse } from "next/server";
import { parsePagination } from "@/lib/utils";
import { listAuditLogs, deleteAllAuditLogs } from "@/lib/db/audit-logs";
import { listUsers, getUsersByIds } from "@/lib/db/users";
import { getProjectsByIds } from "@/lib/db/projects";

const CATEGORY_ENTITIES: Record<string, string[]> = {
  security: ["Auth", "Security"],
  project: ["Project", "Budget", "Risk", "Gate", "Milestone", "ScopeChange"],
  admin: ["User", "Factory", "Category", "Division"],
};

export const GET = withHandler(
  { permission: "VIEW_AUDIT_LOGS", rateLimit: RATE_LIMITS.read },
  async ({ req }) => {
    const url = req.nextUrl;
    const { page, limit, skip } = parsePagination(url.searchParams, { defaultLimit: 25 });
    const category = url.searchParams.get("category") || "all";
    const action = url.searchParams.get("action") || "";
    const userId = url.searchParams.get("userId") || "";
    const from = url.searchParams.get("from") || "";
    const to = url.searchParams.get("to") || "";
    const search = url.searchParams.get("search") || "";

    // audit_logs no longer denormalizes user name/email — resolve matching
    // user ids up front so `search` can also match on user.name / user.email
    // the way the old Prisma `include: { user: ... }` query did.
    let matchingUserIds: string[] | undefined;
    if (search) {
      const { users: matchingUsers } = await listUsers({ search });
      matchingUserIds = matchingUsers.map((u) => u.id);
    }

    let toDate: Date | undefined;
    if (to) {
      toDate = new Date(to);
      toDate.setHours(23, 59, 59, 999);
    }

    const { logs, total } = await listAuditLogs({
      entities: category !== "all" ? CATEGORY_ENTITIES[category] : undefined,
      action: action || undefined,
      userId: userId || undefined,
      from: from ? new Date(from) : undefined,
      to: toDate,
      search: search || undefined,
      matchingUserIds,
      limit,
      offset: skip,
    });

    const userIds = [...new Set(logs.map((l) => l.userId).filter((x): x is string => !!x))];
    const projectIds = [...new Set(logs.map((l) => l.projectId).filter((x): x is string => !!x))];
    const [users, projects] = await Promise.all([
      getUsersByIds(userIds),
      getProjectsByIds(projectIds, "id, name, reference"),
    ]);
    const userById = new Map(users.map((u) => [u.id, u]));
    const projectById = new Map(projects.map((p) => [p.id as string, p]));

    const enriched = logs.map((l) => {
      const u = l.userId ? userById.get(l.userId) : undefined;
      const p = l.projectId ? projectById.get(l.projectId) : undefined;
      return {
        ...l,
        user: u ? { id: u.id, name: u.name, email: u.email } : null,
        project: p ? { id: p.id, name: p.name, reference: p.reference } : null,
      };
    });

    return NextResponse.json({ logs: enriched, total, page, pageSize: limit });
  },
);

export const DELETE = withHandler(
  // Destructive audit-trail wipe is admin-only. VIEW_AUDIT_LOGS is read-only
  // by intent and can be granted to non-admin reviewers — they must not be
  // able to erase security events (LOGIN_FAILED, PERMISSION_CHANGED, etc.).
  { requireAdmin: true, rateLimit: RATE_LIMITS.mutation },
  async ({ user }) => {
    const count = await deleteAllAuditLogs();

    // Log the clear action itself (this will be the first record after clearing)
    await createAuditLog({
      userId: user.id,
      action: "DELETE",
      entity: "AuditLog",
      changes: { recordsCleared: { old: count, new: 0 } },
    });

    return NextResponse.json({ deleted: count });
  },
);
