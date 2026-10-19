import { withHandler, createAuditLog } from "@/lib/api-handler";
import { updateUserSchema, type UpdateUserInput } from "@/lib/validations";
import { RATE_LIMITS } from "@/lib/rate-limit";
import { logSecurityEvent } from "@/lib/security-audit";
import { NextResponse } from "next/server";
import { getUserById, updateUser, deleteUser } from "@/lib/db/users";
import { deleteAssignmentsForUser, countAssignmentsForUsers } from "@/lib/db/assignments";
import { listGrantsForUser, deleteGrantsForUser, createGrant } from "@/lib/db/scope-grants";
import { countRows, findByIds } from "@/lib/db/query-builder";
import { fromRow } from "@/lib/db/rowmap";
import type { User, ScopeGrant, GlobalRole, Permission } from "@/lib/db/models";

interface UserUpdateFields {
  permissions?: Permission[];
  globalRole?: GlobalRole;
  isActive?: boolean;
  name?: string;
}

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

async function countOtherActiveAdmins(excludeUserId: string): Promise<number> {
  return countRows("users", [
    { type: "eq", column: "global_role", value: "ADMIN" },
    { type: "eq", column: "is_active", value: true },
    { type: "neq", column: "id", value: excludeUserId },
  ]);
}

export const PUT = withHandler<UpdateUserInput, { id: string }>(
  {
    permission: "MANAGE_USERS",
    schema: updateUserSchema,
    rateLimit: RATE_LIMITS.mutation,
  },
  async ({ user, params, body }) => {
    const target = await getUserById(params.id);
    if (!target) {
      return NextResponse.json({ error: "User not found" }, { status: 404 });
    }

    // Last-admin / self-lockout safety. Block changes that would leave the
    // system with no active administrators, or that would deactivate /
    // demote the current caller.
    const isSelf = target.id === user.id;
    const willDemote =
      body.globalRole !== undefined &&
      target.globalRole === "ADMIN" &&
      body.globalRole !== "ADMIN";
    const willDeactivate = body.isActive === false && target.isActive;

    if (isSelf && willDeactivate) {
      return NextResponse.json(
        { error: "You can't deactivate your own account." },
        { status: 400 },
      );
    }
    if (isSelf && willDemote) {
      return NextResponse.json(
        { error: "You can't remove your own administrator role." },
        { status: 400 },
      );
    }
    if ((willDemote || willDeactivate) && target.globalRole === "ADMIN" && target.isActive) {
      const otherAdmins = await countOtherActiveAdmins(target.id);
      if (otherAdmins === 0) {
        return NextResponse.json(
          {
            error:
              "Cannot deactivate or demote the last active administrator. Promote another user to ADMIN first.",
          },
          { status: 400 },
        );
      }
    }

    const updateData: UserUpdateFields = {};
    const changes: Record<string, { old: unknown; new: unknown }> = {};

    if (body.permissions !== undefined) {
      updateData.permissions = body.permissions;
      changes.permissions = { old: target.permissions, new: body.permissions };
    }

    if (body.globalRole !== undefined && body.globalRole !== target.globalRole) {
      updateData.globalRole = body.globalRole;
      changes.globalRole = { old: target.globalRole, new: body.globalRole };
    }

    if (body.isActive !== undefined) {
      updateData.isActive = body.isActive;
      changes.isActive = { old: target.isActive, new: body.isActive };
    }

    if (body.name !== undefined) {
      updateData.name = body.name;
      changes.name = { old: target.name, new: body.name };
    }

    // Scope grants: full-replace semantics — the UI sends the complete desired
    // set, so we delete the existing rows and recreate. Cheap (few rows/user)
    // and avoids reconciling diffs.
    if (body.scopeGrants !== undefined) {
      const prior = await listGrantsForUser(params.id);
      const priorNarrow = prior.map((g) => ({ divisionId: g.divisionId, factoryId: g.factoryId }));
      await deleteGrantsForUser(params.id);
      if (body.scopeGrants.length > 0) {
        await Promise.all(
          body.scopeGrants.map((g) =>
            createGrant({
              userId: params.id,
              divisionId: g.divisionId ?? null,
              factoryId: g.factoryId ?? null,
            }),
          ),
        );
      }
      changes.scopeGrants = { old: priorNarrow, new: body.scopeGrants };
    }

    await updateUser(params.id, updateData);

    const updatedTarget = await getUserById(params.id);
    if (!updatedTarget) {
      return NextResponse.json({ error: "User not found" }, { status: 404 });
    }
    const [updated] = await withUserExtras([updatedTarget]);

    await createAuditLog({
      userId: user.id,
      action: "UPDATE",
      entity: "User",
      entityId: params.id,
      changes,
    });

    // Log security-relevant events
    if (body.permissions !== undefined) {
      logSecurityEvent({
        userId: user.id,
        event: "PERMISSION_CHANGED",
        metadata: {
          targetUserId: params.id,
          targetUserName: target.name,
          oldPermissions: target.permissions,
          newPermissions: body.permissions,
        },
      });
    }
    if (body.globalRole !== undefined && body.globalRole !== target.globalRole) {
      logSecurityEvent({
        userId: user.id,
        event: "PERMISSION_CHANGED",
        metadata: {
          targetUserId: params.id,
          targetUserName: target.name,
          oldGlobalRole: target.globalRole,
          newGlobalRole: body.globalRole,
        },
      });
    }
    if (body.isActive !== undefined && body.isActive !== target.isActive) {
      logSecurityEvent({
        userId: user.id,
        event: body.isActive ? "USER_REACTIVATED" : "USER_DEACTIVATED",
        metadata: { targetUserId: params.id, targetUserName: target.name },
      });
    }

    return NextResponse.json(updated);
  },
);

export const DELETE = withHandler<undefined, { id: string }>(
  {
    permission: "MANAGE_USERS",
    rateLimit: RATE_LIMITS.mutation,
  },
  async ({ user, params }) => {
    const target = await getUserById(params.id);
    if (!target) {
      return NextResponse.json({ error: "User not found" }, { status: 404 });
    }

    // Safety rail #1: can't delete yourself — otherwise an admin can lock
    // themselves out and have no way back in.
    if (target.id === user.id) {
      return NextResponse.json(
        { error: "You can't delete your own account." },
        { status: 400 },
      );
    }

    // Safety rail #2: never delete the last remaining active admin —
    // otherwise nobody can ever manage users again.
    if (target.globalRole === "ADMIN" && target.isActive) {
      const otherAdmins = await countOtherActiveAdmins(target.id);
      if (otherAdmins === 0) {
        return NextResponse.json(
          {
            error:
              "Cannot delete the last active administrator. Promote another user to ADMIN first.",
          },
          { status: 400 },
        );
      }
    }

    // Databricks has no FK cascade — clean up dependent rows explicitly
    // before deleting the user itself (NextAuth Account/Session tables no
    // longer exist, so only assignments + scope grants need it).
    await deleteAssignmentsForUser(params.id);
    await deleteGrantsForUser(params.id);
    await deleteUser(params.id);

    await createAuditLog({
      userId: user.id,
      action: "DELETE",
      entity: "User",
      entityId: params.id,
      changes: { name: { old: target.name, new: null } },
    });

    logSecurityEvent({
      userId: user.id,
      event: "USER_DELETED",
      metadata: {
        targetUserId: params.id,
        targetUserName: target.name,
        targetEmail: target.email,
      },
    });

    return NextResponse.json({ deleted: true });
  },
);
