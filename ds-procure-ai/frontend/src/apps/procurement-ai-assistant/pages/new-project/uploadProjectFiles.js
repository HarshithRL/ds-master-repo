import { apiPostForm } from "../../../../services/api";

export async function uploadProjectFiles(projectId, files = []) {
  if (!projectId || files.length === 0) {
    return { uploaded: [] };
  }
  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }
  return apiPostForm(`/api/procurement/projects/${projectId}/files`, formData);
}

export function summarizeUploadResult(uploaded = []) {
  if (!uploaded.length) {
    return "No files uploaded.";
  }
  const count = uploaded.length;
  const parsed = uploaded.filter((item) => item.parseStatus === "ok").length;
  const pending = uploaded.filter((item) => item.parseStatus === "pending").length;
  const failed = uploaded.filter((item) => item.parseStatus === "error").length;
  const skipped = uploaded.filter((item) => item.parseStatus === "skipped").length;
  const noun = count === 1 ? "file" : "files";
  const parts = [`Uploaded ${count} ${noun}`];
  if (pending) {
    parts.push(`${pending} pending parse`);
  }
  if (parsed) {
    parts.push(`${parsed} parsed`);
  }
  if (failed) {
    parts.push(`${failed} failed to parse`);
  }
  if (skipped) {
    parts.push(`${skipped} skipped`);
  }
  return parts.join(" · ");
}

