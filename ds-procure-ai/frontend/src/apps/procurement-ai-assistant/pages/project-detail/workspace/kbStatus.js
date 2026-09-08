export const KB_BUILDING_STATUSES = new Set([
  "ingesting",
  "building",
  "staged",
  "extracting",
]);

export function kbIsBuilding(status) {
  return KB_BUILDING_STATUSES.has(status);
}

export function kbStatusCopy(status, message) {
  const trimmed = (message || "").trim();
  if (trimmed) {
    return trimmed;
  }
  if (status === "ingesting") {
    return "Parsing uploaded files…";
  }
  if (status === "building" || status === "extracting" || status === "staged") {
    return "Building knowledge base — extracting vendor evidence…";
  }
  if (status === "failed") {
    return "Knowledge base build failed.";
  }
  if (status === "needs_review") {
    return "Knowledge base needs review.";
  }
  if (status === "ready") {
    return "Knowledge base ready.";
  }
  return null;
}
