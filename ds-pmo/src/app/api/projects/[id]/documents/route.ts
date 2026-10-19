import { withHandler, createAuditLog } from "@/lib/api-handler";
import { createDocumentSchema, type CreateDocumentInput } from "@/lib/validations";
import { RATE_LIMITS } from "@/lib/rate-limit";
import { getProjectBasic } from "@/lib/db/projects";
import { listDocumentsForProject, createDocument } from "@/lib/db/documents";
import { NextResponse } from "next/server";

export const GET = withHandler<undefined, { id: string }>(
  { projectAccess: true, rateLimit: RATE_LIMITS.read },
  async ({ params }) => {
    const project = await getProjectBasic(params.id);
    if (!project) {
      return NextResponse.json({ error: "Project not found" }, { status: 404 });
    }

    const documents = await listDocumentsForProject(params.id);
    return NextResponse.json(documents);
  },
);

export const POST = withHandler<CreateDocumentInput, { id: string }>(
  {
    projectAccess: true,
    schema: createDocumentSchema,
    rateLimit: RATE_LIMITS.mutation,
  },
  async ({ user, params, body }) => {
    const project = await getProjectBasic(params.id);
    if (!project) {
      return NextResponse.json({ error: "Project not found" }, { status: 404 });
    }

    const existing = await listDocumentsForProject(params.id);
    const last = existing.reduce<{ sortOrder: number } | null>((max, d) => {
      return !max || d.sortOrder > max.sortOrder ? d : max;
    }, null);

    const document = await createDocument({
      projectId: params.id,
      name: body.name,
      url: body.url,
      sortOrder: (last?.sortOrder || 0) + 1,
    });

    await createAuditLog({
      userId: user.id,
      projectId: params.id,
      action: "CREATE",
      entity: "ProjectDocument",
      entityId: document.id,
      changes: {
        name: { old: null, new: body.name },
        url: { old: null, new: body.url },
      },
    });

    return NextResponse.json(document, { status: 201 });
  },
);
