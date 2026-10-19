import { withHandler, createAuditLog } from "@/lib/api-handler";
import { createRiskSchema, type CreateRiskInput } from "@/lib/validations";
import { RATE_LIMITS } from "@/lib/rate-limit";
import { getProjectRaw } from "@/lib/db/projects";
import { listRisksForProject, createRisk } from "@/lib/db/risks";
import { NextResponse } from "next/server";

export const GET = withHandler<undefined, { id: string }>(
  { projectAccess: true, rateLimit: RATE_LIMITS.read },
  async ({ params }) => {
    const project = await getProjectRaw(params.id);
    if (!project) {
      return NextResponse.json({ error: "Project not found" }, { status: 404 });
    }

    const risks = await listRisksForProject(params.id);
    risks.sort((a, b) => {
      const impactOrder: Record<string, number> = { HIGH: 2, MODERATE: 1, LOW: 0 };
      const impactDiff = (impactOrder[b.impact] ?? 0) - (impactOrder[a.impact] ?? 0);
      if (impactDiff !== 0) return impactDiff;
      return b.createdAt.getTime() - a.createdAt.getTime();
    });
    return NextResponse.json(risks);
  },
);

export const POST = withHandler<CreateRiskInput, { id: string }>(
  {
    projectAccess: true,
    schema: createRiskSchema,
    rateLimit: RATE_LIMITS.mutation,
  },
  async ({ user, params, body }) => {
    const project = await getProjectRaw(params.id);
    if (!project) {
      return NextResponse.json({ error: "Project not found" }, { status: 404 });
    }

    // Auto-parse IF/DUE TO/THEN from riskStatement if clauses not provided
    let ifClause = body.ifClause;
    let dueToClause = body.dueToClause;
    let thenClause = body.thenClause;

    if (body.riskStatement && !ifClause && !dueToClause && !thenClause) {
      const ifMatch = body.riskStatement.match(/IF\s+(.+?)\s+DUE\s+TO/i);
      const dueMatch = body.riskStatement.match(/DUE\s+TO\s+(.+?)\s+THEN/i);
      const thenMatch = body.riskStatement.match(/THEN\s+(.+)$/i);
      if (ifMatch) ifClause = ifMatch[1].trim();
      if (dueMatch) dueToClause = dueMatch[1].trim();
      if (thenMatch) thenClause = thenMatch[1].trim();
    }

    const risk = await createRisk({
      projectId: params.id,
      riskStatement: body.riskStatement,
      ifClause,
      dueToClause,
      thenClause,
      type: body.type,
      impact: body.impact,
      probability: body.probability,
      costImpact: body.costImpact,
      timeImpact: body.timeImpact,
      counterMeasures: body.counterMeasures,
      ownerName: body.ownerName || null,
    });

    await createAuditLog({
      userId: user.id,
      projectId: params.id,
      action: "CREATE",
      entity: "Risk",
      entityId: risk.id,
      changes: {
        riskStatement: { old: null, new: body.riskStatement },
        impact: { old: null, new: body.impact },
      },
    });

    return NextResponse.json(risk, { status: 201 });
  },
);
