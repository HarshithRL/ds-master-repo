import { useEffect, useState } from "react";
import { apiGet } from "../../../../services/api";
import { kbIsBuilding } from "./workspace/kbStatus";

const POLL_MS = 4000;

export function useProjectView(projectId, path) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    if (!projectId) {
      return undefined;
    }
    let cancelled = false;
    let timer = 0;
    setData(null);
    setError(null);

    function load() {
      apiGet(`/api/procurement/projects/${projectId}${path}`)
        .then((payload) => {
          if (cancelled) {
            return;
          }
          setData(payload);
          setError(null);
          if (kbIsBuilding(payload?.kb_status)) {
            timer = window.setTimeout(load, POLL_MS);
          }
        })
        .catch(() => {
          if (cancelled) {
            return;
          }
          setError("Unable to load.");
        });
    }

    load();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [projectId, path, reloadToken]);

  return { data, error, refresh: () => setReloadToken((n) => n + 1) };
}
