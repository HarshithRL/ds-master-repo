import { getUserById } from "./db/users";
import { listAssignmentsForUser } from "./db/assignments";
import { listAuditLogs } from "./db/audit-logs";
import { getProjectsByIds } from "./db/projects";
import { countSnapshotsCreatedBy } from "./db/snapshots";
import { countGatesUpdatedBy } from "./db/gates";

/**
 * One query bundle for every "person dossier" view — used by
 *   /profile           (logged-in user looking at themselves)
 *   /admin/users/[id]  (admin looking at any user)
 *
 * Same shape for both so they share the <ProfileView> component.
 * Returns null if the user doesn't exist.
 */
export async function fetchProfileData(userId: string) {
  // Sponsor/Owner/PM/PMO all live in ProjectAssignment now, so the single
  // assignments query covers what used to be three separate fetches.
  const [user, assignments, recentActivity, snapshotCount, gateCount] = await Promise.all([
    getUserById(userId),
    listAssignmentsForUser(userId),
    listAuditLogs({ userId, limit: 10 }),
    countSnapshotsCreatedBy(userId),
    countGatesUpdatedBy(userId),
  ]);

  if (!user) return null;

  type ProjectStub = { id: string; reference: string | null; name: string; currentPhase: string; isActive: boolean };
  type ActivityProjectStub = { id: string; reference: string | null; name: string };

  const projects = await getProjectsByIds(
    assignments.map((a) => a.projectId),
    "id, reference, name, current_phase, is_active",
  );
  const projectsById = new Map(projects.map((p) => [p.id as string, p as unknown as ProjectStub]));
  // Assignments whose project no longer exists (orphaned data — no enforced FK)
  // are dropped rather than surfaced with a null project.
  const assignmentsWithProject = assignments
    .slice()
    .sort((a, b) => b.createdAt.getTime() - a.createdAt.getTime())
    .flatMap((a) => {
      const project = projectsById.get(a.projectId);
      return project ? [{ ...a, project }] : [];
    });

  const projectIdsForActivity = [...new Set(recentActivity.logs.map((l) => l.projectId).filter((x): x is string => !!x))];
  const activityProjects = await getProjectsByIds(projectIdsForActivity, "id, reference, name");
  const activityProjectsById = new Map(activityProjects.map((p) => [p.id as string, p as unknown as ActivityProjectStub]));
  const recentActivityWithProject = recentActivity.logs.map((l) => ({
    ...l,
    project: l.projectId ? (activityProjectsById.get(l.projectId) ?? null) : null,
  }));

  return {
    user,
    assignments: assignmentsWithProject,
    recentActivity: recentActivityWithProject,
    counters: { snapshots: snapshotCount, gates: gateCount },
  };
}
