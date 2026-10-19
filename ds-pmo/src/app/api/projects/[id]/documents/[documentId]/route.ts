import { withHandler, createAuditLog } from "@/lib/api-handler";
import { updateDocumentSchema, type UpdateDocumentInput } from "@/lib/validations";
import { RATE_LIMITS } from "@/lib/rate-limit";
import { getDocumentById, updateDocument, deleteDocument } from "@/lib/db/documents";
import { NextResponse } from "next/server";

type Params = { id: string; documentId: string };

export const PUT = withHandler<UpdateDocumentInput, Params>(
  {
    projectAccess: true,
    schema: updateDocumentSchema,
    rateLimit: RATE_LIMITS.mutation,
  },
  async ({ user, params, body }) => {
    const document = await getDocumentById(params.documentId);
    if (!document || document.projectId !== params.id) {
      return NextResponse.json({ error: "Document not found" }, { status: 404 });
    }

    const updateData: Record<string, unknown> = {};
    if (body.name !== undefined) updateData.name = body.name;
    if (body.url !== undefined) updateData.url = body.url;

    await updateDocument(params.documentId, updateData);

    const changes: Record<string, { old: unknown; new: unknown }> = {};
    for (const key of Object.keys(updateData)) {
      changes[key] = {
        old: (document as unknown as Record<string, unknown>)[key],
        new: updateData[key],
      };
    }

    await createAuditLog({
      userId: user.id,
      projectId: params.id,
      action: "UPDATE",
      entity: "ProjectDocument",
      entityId: params.documentId,
      changes,
    });

    const updated = await getDocumentById(params.documentId);
    return NextResponse.json(updated);
  },
);

export const DELETE = withHandler<undefined, Params>(
  { projectAccess: true, rateLimit: RATE_LIMITS.mutation },
  async ({ user, params }) => {
    const document = await getDocumentById(params.documentId);
    if (!document || document.projectId !== params.id) {
      return NextResponse.json({ error: "Document not found" }, { status: 404 });
    }

    await deleteDocument(params.documentId);

    await createAuditLog({
      userId: user.id,
      projectId: params.id,
      action: "DELETE",
      entity: "ProjectDocument",
      entityId: params.documentId,
      changes: { name: { old: document.name, new: null } },
    });

    return NextResponse.json({ success: true });
  },
);
