import { selectRows, selectOne, insertRow, updateRow, deleteRows, readBackWithRetry } from "./query-builder";
import { fromRow, toRow } from "./rowmap";
import type { ProjectDocument } from "./models";

const TABLE = "project_documents";

function map(row: Record<string, unknown>): ProjectDocument {
  return fromRow<ProjectDocument>(row);
}

export async function listDocumentsForProject(projectId: string): Promise<ProjectDocument[]> {
  const rows = await selectRows<Record<string, unknown>>(TABLE, {
    where: [{ type: "eq", column: "project_id", value: projectId }],
    orderBy: [{ column: "sort_order", direction: "ASC" }],
  });
  return rows.map(map);
}

export async function getDocumentById(id: string): Promise<ProjectDocument | null> {
  const row = await selectOne<Record<string, unknown>>(TABLE, { where: [{ type: "eq", column: "id", value: id }] });
  return row ? map(row) : null;
}

export interface DocumentInput {
  projectId: string;
  name: string;
  url: string;
  sortOrder?: number;
}

export async function createDocument(input: DocumentInput): Promise<ProjectDocument> {
  const now = new Date();
  const id = await insertRow(TABLE, toRow({ sortOrder: 0, ...input, createdAt: now, updatedAt: now }));
  return readBackWithRetry(() => getDocumentById(id), "Failed to read back created document");
}

export async function updateDocument(id: string, fields: Partial<DocumentInput>): Promise<void> {
  await updateRow(TABLE, id, toRow({ ...fields, updatedAt: new Date() }));
}

export async function deleteDocument(id: string): Promise<void> {
  await deleteRows(TABLE, [{ type: "eq", column: "id", value: id }]);
}
