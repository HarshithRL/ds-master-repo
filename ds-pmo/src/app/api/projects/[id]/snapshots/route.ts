import { withHandler } from "@/lib/api-handler";
import { RATE_LIMITS } from "@/lib/rate-limit";
import { listSnapshotsForProject } from "@/lib/db/snapshots";
import { getUsersByIds } from "@/lib/db/users";
import { NextResponse } from "next/server";

export const GET = withHandler<undefined, { id: string }>(
  { projectAccess: true, rateLimit: RATE_LIMITS.read },
  async ({ params }) => {
    const snapshots = await listSnapshotsForProject(params.id);
    const userIds = [...new Set(snapshots.map((s) => s.createdById).filter((id): id is string => !!id))];
    const users = await getUsersByIds(userIds);
    const usersById = new Map(users.map((u) => [u.id, u]));

    const withCreatedBy = snapshots.map((s) => ({
      ...s,
      createdBy: s.createdById
        ? (() => {
            const u = usersById.get(s.createdById!);
            return u ? { id: u.id, name: u.name, email: u.email } : null;
          })()
        : null,
    }));

    return NextResponse.json(withCreatedBy);
  },
);
