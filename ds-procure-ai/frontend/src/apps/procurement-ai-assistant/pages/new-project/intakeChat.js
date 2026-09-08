export const OPENER = "Let’s start a sourcing project.";

export const PROCESS_PROMPT = "Which business process is this buy?";

export const GREET_TRIGGER =
  "The user just created this sourcing project and opened the workspace chat. Greet them warmly, welcome them to this project, and ask if they want you to guide them step by step (confirm or set project name, choose workflow, upload vendor documents, then comparison). Keep it short. Do not invent facts that are not in the project knowledge header.";

export function uploadFilesTrigger(uploaded = []) {
  const names = uploaded
    .map((item) => item?.name || item?.original_name || "")
    .map((name) => String(name).trim())
    .filter(Boolean);
  const list = names.length
    ? names.join(", ")
    : `${uploaded.length || 0} file(s)`;
  return (
    "The user just uploaded these files into this project workspace: " +
    `${list}. ` +
    "Parse and knowledge-base build are running in the background. " +
    "Acknowledge the upload briefly, name the files, say the knowledge base is still building, " +
    "and offer the next step (wait for parse, missing docs, or comparison) without inventing prices or scores. Keep it short."
  );
}

export function intakeSeedKey(projectUuid) {
  return `mate-intake-messages:${projectUuid}`;
}

export function writeIntakeSeed(projectUuid, payload) {
  try {
    sessionStorage.setItem(intakeSeedKey(projectUuid), JSON.stringify(payload));
  } catch {
    /* ignore quota / private mode */
  }
}

export function readIntakeSeed(projectUuid) {
  try {
    const raw = sessionStorage.getItem(intakeSeedKey(projectUuid));
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

export function intakePendingSentKey(projectUuid) {
  return `mate-intake-pending-sent:${projectUuid}`;
}

export function clearIntakePending(projectUuid) {
  try {
    const raw = sessionStorage.getItem(intakeSeedKey(projectUuid));
    if (!raw) return;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return;
    writeIntakeSeed(projectUuid, { ...parsed, pendingMessage: "" });
  } catch {
    /* ignore */
  }
}

export function markIntakePendingSent(projectUuid) {
  try {
    sessionStorage.setItem(intakePendingSentKey(projectUuid), "1");
  } catch {
    /* ignore */
  }
  clearIntakePending(projectUuid);
}

export function wasIntakePendingSent(projectUuid) {
  try {
    return sessionStorage.getItem(intakePendingSentKey(projectUuid)) === "1";
  } catch {
    return false;
  }
}
