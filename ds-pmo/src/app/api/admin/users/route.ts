import { withHandler, createAuditLog } from "@/lib/api-handler";
import { createAdminUserSchema, type CreateAdminUserInput } from "@/lib/validations";
import { RATE_LIMITS } from "@/lib/rate-limit";
import { logSecurityEvent } from "@/lib/security-audit";
import { sendEmailAsync, welcomeEmail } from "@/lib/email";
import { NextResponse } from "next/server";
import { listUsers, getUserByEmail, createUser } from "@/lib/db/users";
import { countAssignmentsForUsers } from "@/lib/db/assignments";
import { createGrant } from "@/lib/db/scope-grants";
import { findByIds } from "@/lib/db/query-builder";
import { fromRow } from "@/lib/db/rowmap";
import type { User, ScopeGrant } from "@/lib/db/models";

/** Mirrors the old Prisma `USER_INCLUDE`: `_count.assignments` + narrow `scopeGrants`. */
async function withUserExtras(users: User[]) {
  const ids = users.map((u) => u.id);
  const [counts, grantRows] = await Promise.all([
    countAssignmentsForUsers(ids),
    findByIds<Record<string, unknown>>("scope_grants", "user_id", ids),
  ]);
  const grants = grantRows.map((r) => fromRow<ScopeGrant>(r));
  const grantsByUser = new Map<string, ScopeGrant[]>();
  for (const g of grants) {
    const list = grantsByUser.get(g.userId);
    if (list) list.push(g);
    else grantsByUser.set(g.userId, [g]);
  }
  return users.map((u) => ({
    ...u,
    _count: { assignments: counts.get(u.id) ?? 0 },
    scopeGrants: (grantsByUser.get(u.id) ?? []).map((g) => ({
      id: g.id,
      divisionId: g.divisionId,
      factoryId: g.factoryId,
    })),
  }));
}

export const GET = withHandler(
  { permission: "MANAGE_USERS", rateLimit: RATE_LIMITS.read },
  async () => {
    const { users } = await listUsers({});
    const withExtras = await withUserExtras(users);
    return NextResponse.json(withExtras);
  },
);

export const POST = withHandler<CreateAdminUserInput>(
  {
    permission: "MANAGE_USERS",
    schema: createAdminUserSchema,
    rateLimit: RATE_LIMITS.mutation,
  },
  async ({ user, body }) => {
    if (body.email) {
      const existing = await getUserByEmail(body.email);
      if (existing) {
        return NextResponse.json(
          { error: "User already exists" },
          { status: 409 },
        );
      }
    }

    const newUser = await createUser({
      name: body.name.trim(),
      email: body.email?.trim() || null,
      globalRole: body.globalRole,
      permissions: body.permissions ?? [],
      isActive: true,
    });

    if (body.scopeGrants?.length) {
      await Promise.all(
        body.scopeGrants.map((g) =>
          createGrant({
            userId: newUser.id,
            divisionId: g.divisionId ?? null,
            factoryId: g.factoryId ?? null,
          }),
        ),
      );
    }

    const [newUserWithExtras] = await withUserExtras([newUser]);

    await createAuditLog({
      userId: user.id,
      action: "CREATE",
      entity: "User",
      entityId: newUser.id,
      changes: {
        name: { old: null, new: body.name },
        email: { old: null, new: body.email ?? null },
      },
    });

    logSecurityEvent({
      userId: user.id,
      event: "USER_CREATED",
      metadata: {
        targetUserId: newUser.id,
        targetUserName: body.name,
        targetEmail: body.email,
        permissions: body.permissions ?? [],
      },
    });

    // Send welcome email (fire-and-forget)
    if (newUser.email) {
      const baseUrl = process.env.AUTH_URL || "http://localhost:3000";
      const template = welcomeEmail({
        name: newUser.name,
        email: newUser.email,
        loginUrl: `${baseUrl}/login`,
      });
      sendEmailAsync({
        to: newUser.email,
        category: "notification",
        ...template,
      });
    }

    return NextResponse.json(newUserWithExtras, { status: 201 });
  },
);
