"use client";

import { useCallback, useEffect, useState } from "react";
import { invalidateReferenceData } from "@/hooks/use-reference-data";

/* ═══════════════════════════════════════════════════════════════════
   useAdminResource — list/add/update/remove for the admin CRUD screens.

   Backs UsersAdmin, FactoriesAdmin (via SimpleCrudAdmin), CategoriesAdmin
   (via SimpleCrudAdmin) — same fetch/error/state shape, written once.
   ═══════════════════════════════════════════════════════════════════ */

type WithId = { id: string };

export interface UseAdminResourceOptions {
  /** Base REST endpoint (POST {}, PUT {id}, DELETE {id}). */
  endpoint: string;
  /** Whether to clear the global reference-data cache after writes. */
  invalidatesReferenceData?: boolean;
}

export interface UseAdminResource<T extends WithId> {
  rows: T[];
  setRows: React.Dispatch<React.SetStateAction<T[]>>;
  loading: boolean;
  error: string | null;
  setError: (e: string | null) => void;
  reload: () => Promise<void>;
  add: <B = unknown>(body: B) => Promise<T | null>;
  update: <B = unknown>(id: string, body: B) => Promise<T | null>;
  remove: (id: string) => Promise<boolean>;
}

export function useAdminResource<T extends WithId>({
  endpoint,
  invalidatesReferenceData: invalidate = true,
}: UseAdminResourceOptions): UseAdminResource<T> {
  const [rows, setRows] = useState<T[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(endpoint);
      if (!res.ok) throw new Error("Failed to load");
      const data: T[] = await res.json();
      setRows(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [endpoint]);

  useEffect(() => {
    reload();
  }, [reload]);

  const afterWrite = () => {
    if (invalidate) invalidateReferenceData();
  };

  const add = useCallback(
    async <B,>(body: B): Promise<T | null> => {
      try {
        const res = await fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const json = await res.json();
        if (!res.ok) throw new Error(json.error || "Failed to create");
        setRows((p) => [...p, json]);
        setError(null);
        afterWrite();
        return json;
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to create");
        return null;
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [endpoint, invalidate],
  );

  const update = useCallback(
    async <B,>(id: string, body: B): Promise<T | null> => {
      try {
        const res = await fetch(`${endpoint}/${id}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const json = await res.json();
        if (!res.ok) throw new Error(json.error || "Failed to update");
        setRows((p) => p.map((r) => (r.id === id ? (json as T) : r)));
        setError(null);
        afterWrite();
        return json;
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to update");
        return null;
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [endpoint, invalidate],
  );

  const remove = useCallback(
    async (id: string): Promise<boolean> => {
      try {
        const res = await fetch(`${endpoint}/${id}`, { method: "DELETE" });
        if (!res.ok) {
          const json = await res.json().catch(() => ({}));
          throw new Error(json.error || "Failed to remove");
        }
        setRows((p) => p.filter((r) => r.id !== id));
        setError(null);
        afterWrite();
        return true;
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to remove");
        return false;
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [endpoint, invalidate],
  );

  return { rows, setRows, loading, error, setError, reload, add, update, remove };
}
