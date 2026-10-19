import { withHandler } from "@/lib/api-handler";
import { computePortfolio, type PortfolioInput } from "@/lib/compute-portfolio";
import { RATE_LIMITS } from "@/lib/rate-limit";
import { visibleProjectsWhere, confidentialProjectAccess } from "@/lib/access-control";
import { calcScheduleBufferDays } from "@/lib/calculations";
import { listProjectRows, attachListRelations } from "@/lib/db/projects";
import { NextResponse } from "next/server";

export const GET = withHandler(
  { rateLimit: RATE_LIMITS.read },
  async ({ user }) => {
    // Scope to projects this user is allowed to see. ADMIN/PMO/EXECUTIVE
    // get the full portfolio; MEMBER gets their slice (so PMs see a real
    // dashboard scoped to their projects instead of a 403).
    const [visibility, confidentialAccess] = await Promise.all([
      visibleProjectsWhere(user),
      confidentialProjectAccess(user),
    ]);
    // includeInactive defaults to false, matching the old isActive: true filter.
    const rows = await listProjectRows({ visibility, confidentialAccess });
    const projects = await attachListRelations(rows);

    // scheduleBuffer is derived live — see lib/project-derive.ts. Attaching
    // it here keeps computePortfolio's input shape unchanged.
    const withDerivedBuffer = projects.map((p) => {
      const project = p as unknown as PortfolioInput & {
        plannedCompletionDate: Date | string | null;
        expectedCompletionDate: Date | string | null;
      };
      return {
        ...project,
        scheduleBuffer: calcScheduleBufferDays(project.plannedCompletionDate, project.expectedCompletionDate),
      };
    });

    return NextResponse.json(computePortfolio(withDerivedBuffer));
  },
);
