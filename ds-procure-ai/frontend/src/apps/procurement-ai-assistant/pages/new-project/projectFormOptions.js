export const WORKFLOW_ENTRY_POINTS = [
  "Sourcing",
  "Vendor Comparison",
  "Contract Negotiation",
];

export const EMPTY_BRIEF = {
  name: "",
  workflowEntryPoint: "",
  businessProcess: "",
  requester: "",
  dept: "",
  targetSpend: "",
  category: "",
  awardHorizon: "",
  region: "",
  description: "",
};

export function canCreateProject({
  projectId,
  submitting,
  loadingProjectId,
}) {
  return Boolean(projectId?.trim()) && !submitting && !loadingProjectId;
}

export function createProjectPayload(projectId, brief, requirements = []) {
  const payload = {
    ...(projectId?.trim() ? { projectId: projectId.trim() } : {}),
  };
  const fields = [
    "name",
    "workflowEntryPoint",
    "businessProcess",
    "requester",
    "dept",
    "targetSpend",
    "category",
    "awardHorizon",
    "region",
    "description",
  ];
  for (const field of fields) {
    const value = String(brief?.[field] || "").trim();
    if (value) {
      payload[field] = value;
    }
  }
  const rows = Array.isArray(requirements) ? requirements : [];
  const mapped = [];
  for (const row of rows) {
    const ref = row.ref;
    const text = row.text;
    const weight = row.weight;
    if (String(text || "").trim() || String(ref || "").trim()) {
      mapped.push({ ref, text, weight });
    }
  }
  if (mapped.length > 0) {
    payload.requirements = mapped;
  }
  return payload;
}
