import { apiGet, apiPost } from "../../../../services/api";
import { PROJECTS_LIST_PATH } from "./paths";
import { uploadProjectFiles } from "./uploadProjectFiles";

export async function fetchNextProjectCode() {
  const data = await apiGet("/api/procurement/projects/next-code");
  return data.projectId;
}

export async function createProject(payload, files = []) {
  const created = await apiPost("/api/procurement/projects", payload);

  if (files.length > 0) {
    await uploadProjectFiles(created.id, files);
  }

  return {
    id: created.id,
    name: created.name,
    projectId: created.projectId,
    href: `${PROJECTS_LIST_PATH}/${created.id}`,
  };
}
