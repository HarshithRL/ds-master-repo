import { useCallback, useEffect, useState } from "react";

import { apiGet, apiPost } from "../../../../../../services/api";
import { shouldContinueInsightsPoll } from "../kbStatus";

export const INSIGHTS_POLL_MS = 4000;

export function analysisRoutes(projectId) {
  const base = `/api/procurement/projects/${projectId}`;
  return {
    insights: `${base}/insights`,
    packs: `${base}/packs`,
    pack: (kind) => `${base}/packs/${kind}`,
    download: (kind) => `${base}/packs/${kind}/download`,
  };
}

export function useChatAnalysis(
  projectId,
  { refreshToken = 0, onInsights, uploading = false } = {},
) {
  const [insights, setInsights] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState("");
  const [skippedGaps, setSkippedGaps] = useState(false);

  const applyPayload = useCallback(
    (payload) => {
      setInsights(payload);
      setError(null);
      onInsights?.(payload);
    },
    [onInsights],
  );

  const refresh = useCallback(() => {
    if (!projectId) return Promise.resolve();
    return apiGet(analysisRoutes(projectId).insights)
      .then(applyPayload)
      .catch(() => setError("Unable to load analysis."));
  }, [projectId, applyPayload]);

  useEffect(() => {
    setInsights(null);
    setError(null);
    setBusy("");
    setSkippedGaps(false);
  }, [projectId]);

  useEffect(() => {
    if (!projectId) return undefined;
    let cancelled = false;
    let timer = 0;

    function load() {
      apiGet(analysisRoutes(projectId).insights)
        .then((payload) => {
          if (cancelled) return;
          applyPayload(payload);
          if (shouldContinueInsightsPoll(payload?.kb_status, uploading)) {
            timer = window.setTimeout(load, INSIGHTS_POLL_MS);
          }
        })
        .catch(() => {
          if (!cancelled) setError("Unable to load analysis.");
        });
    }

    load();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [projectId, refreshToken, uploading, applyPayload]);

  async function buildPack(kind) {
    if (!projectId) return;
    setBusy(kind);
    try {
      await apiPost(analysisRoutes(projectId).pack(kind), {});
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
