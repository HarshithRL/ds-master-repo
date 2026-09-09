export const PROJECTS_LIST_PATH = "/app/procurement-ai-assistant/projects";

export function projectWorkspacePath(projectUuid) {
  return `${PROJECTS_LIST_PATH}/${projectUuid}?tab=workspace`;
}
