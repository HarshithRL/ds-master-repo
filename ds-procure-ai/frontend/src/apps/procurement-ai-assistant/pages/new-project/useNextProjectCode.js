import { useEffect, useState } from "react";

import { fetchNextProjectCode } from "./createProject";

export function useNextProjectCode(enabled = true) {
  const [projectId, setProjectId] = useState("");
  const [loadingProjectId, setLoadingProjectId] = useState(Boolean(enabled));
  const [loadError, setLoadError] = useState(null);

  useEffect(() => {
    if (!enabled) {
      setProjectId("");
      setLoadingProjectId(false);
      setLoadError(null);
      return undefined;
    }

    let cancelled = false;
    async function loadProjectId() {
      setLoadingProjectId(true);
      setProjectId("");
      try {
        const code = await fetchNextProjectCode();
        if (!cancelled) {
          setProjectId(code);
          setLoadError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setLoadError(
            err instanceof Error ? err.message : "Unable to load project ID.",
          );
        }
      } finally {
        setLoadingProjectId(false);
      }
    }
    loadProjectId();
    return () => {
      cancelled = true;
    };
  }, [enabled]);

  return { projectId, loadingProjectId, loadError };
}
