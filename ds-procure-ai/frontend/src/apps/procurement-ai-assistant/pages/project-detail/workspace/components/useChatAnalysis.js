import { useCallback, useEffect, useState } from "react";

import { apiGet, apiPost } from "../../../../../../services/api";

export function analysisRoutes(projectId) {
  const base = `/api/procurement/projects/${projectId}`;
  return {
    insights: `${base}/insights`,
    packs: `${base}/packs`,
    pack: (kind) => `${base}/packs/${kind}`,
    download: (kind) => `${base}/packs/${kind}/download`,
  };
}

export function useChatAnalysis(projectId, { refreshToken = 0, onInsights } = {}) {
  const [insights, setInsights] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState("");
  const [skippedGaps, setSkippedGaps] = useState(false);

  const refresh = useCallback(() => {
    if (!projectId) return undefined;
    return apiGet(analysisRoutes(projectId).insights)
      .then((payload) => {
        setInsights(payload);
        setError(null);
        onInsights?.(payload);
      })
      .catch(() => setError("Unable to load analysis."));
  }, [projectId, onInsights]);

  useEffect(() => {
    setInsights(null);
    setError(null);
    setBusy("");
    setSkippedGaps(false);
  }, [projectId]);

  useEffect(() => {
    refresh();
  }, [refresh, refreshToken]);

  useEffect(() => {
    if (!projectId) return undefined;
    const id = window.setInterval(() => {
      refresh();
    }, 4000);
    return () => window.clearInterval(id);
  }, [projectId, refresh]);

  async function buildPack(kind) {
    if (!projectId) return;
    setBusy(kind);
    setError("");
    try {
      const result = await apiPost(analysisRoutes(projectId).pack(kind), {});
      // The POST succeeds either way, so without this the click looks ignored.
      if (kind === "kb" && result?.procurement?.kb_already_running) {
        setError(
          "A knowledge base build is already running. Wait for it to finish before starting another.",
        );
      }
      await refresh();
    } catch (err) {
      setError(err?.message || "Pack build failed.");
    } finally {
      setBusy("");
    }
  }

  return {
    insights,
    error,
    busy,
    skippedGaps,
    skipGaps: () => setSkippedGaps(true),
    buildPack,
    downloadPath: (kind) => (projectId ? analysisRoutes(projectId).download(kind) : ""),
  };
}
