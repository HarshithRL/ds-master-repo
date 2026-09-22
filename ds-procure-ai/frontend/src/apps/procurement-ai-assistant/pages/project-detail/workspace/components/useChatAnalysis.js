import { useCallback, useEffect, useRef, useState } from "react";

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
  const inFlight = useRef(false);
  const everLoaded = useRef(false);

  const refresh = useCallback(
    (force = false) => {
      if (!projectId) return undefined;
      // Polling is faster than the slowest response, so without this the
      // requests stack up on a project that is already slow to answer.
      if (!force && inFlight.current) return undefined;
      inFlight.current = true;
      return apiGet(analysisRoutes(projectId).insights)
        .then((payload) => {
          everLoaded.current = true;
          setInsights(payload);
          setError(null);
          onInsights?.(payload);
        })
        .catch(() => {
          // A deploy or one slow call should not replace a populated panel
          // with an error banner; the next tick almost always succeeds.
          if (!everLoaded.current) setError("Unable to load analysis.");
        })
        .finally(() => {
          inFlight.current = false;
        });
    },
    [projectId, onInsights],
  );

  useEffect(() => {
    setInsights(null);
    setError(null);
    setBusy("");
    setSkippedGaps(false);
    everLoaded.current = false;
    inFlight.current = false;
  }, [projectId]);

  useEffect(() => {
    refresh(true);
  }, [refresh, refreshToken]);

  useEffect(() => {
    if (!projectId) return undefined;
    const id = window.setInterval(() => {
      refresh();
    }, 4000);
    return () => window.clearInterval(id);
  }, [projectId, refresh]);

  async function buildPack(kind, { clearReviews = false } = {}) {
    if (!projectId) return;
    setBusy(kind);
    setError("");
    try {
      const result = await apiPost(analysisRoutes(projectId).pack(kind), {
        clear_reviews: clearReviews,
      });
      // Refresh first: it clears `error` on success, which would otherwise
      // wipe the notice below the moment it is set.
      await refresh(true);
      // The POST succeeds either way, so without this the click looks ignored.
      if (kind === "kb" && result?.procurement?.kb_already_running) {
        setError(
          "A knowledge base build is already running. Wait for it to finish before starting another.",
        );
      }
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
