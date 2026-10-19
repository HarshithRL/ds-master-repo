"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { api } from "@/lib/api";
import { useSaveStatus, SAVE_DEBOUNCE_MS } from "@/hooks/use-save-status";

/**
 * Shared optimistic CRUD for list-based tabs (risks, milestones, etc.).
 *
 * - `add` inserts a temp row instantly, swaps in the real record once the
 *   server responds. Rolls back on failure.
 * - `patch` applies the field change to local state instantly, then schedules
 *   a debounced PUT for that row. Multiple field changes on the same row
 *   within the debounce window are batched into one request.
 *   Reverts only the changed fields on failure (no full project refetch).
 * - `remove` hides the row immediately, rolls back on failure.
 */
export function useOptimisticList<T extends { id: string }>(opts: {
  /** Initial items from the parent (server data). */
  initial: T[];
  /** Base URL for the collection, e.g. `/api/projects/123/risks`. */
  baseUrl: string;
  /** Factory that returns a temp row with a temp `id` + defaults. */
  createOptimistic: () => T;
  /** POST body for the server (derived from the optimistic row). */
  createPayload: (item: T) => Record<string, unknown>;
}) {
  const { initial, baseUrl, createOptimistic, createPayload } = opts;
  const [items, setItems] = useState<T[]>(initial ?? []);
  const { saving, saved, saveFailed } = useSaveStatus();

  // Per-row pending fields + revert snapshot + flush timer + AbortController.
  const pendingByRow = useRef<Map<string, Record<string, unknown>>>(new Map());
  const revertByRow = useRef<Map<string, Record<string, unknown>>>(new Map());
  const timerByRow = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());
  const abortByRow = useRef<Map<string, AbortController>>(new Map());

  useEffect(() => setItems(initial ?? []), [initial]);

  /* ── Add (optimistic) ──────────────────────────────────────── */

  const add = useCallback(async () => {
    const temp = createOptimistic();
    setItems((prev) => [...prev, temp]);

    try {
      const real = await api.post<T>(baseUrl, createPayload(temp));
      // Swap temp → real
      setItems((prev) => prev.map((i) => (i.id === temp.id ? real : i)));
      saved();
    } catch {
      // Roll back the temp row
      setItems((prev) => prev.filter((i) => i.id !== temp.id));
      saveFailed();
    }
  }, [baseUrl, createOptimistic, createPayload, saved, saveFailed]);

  /* ── Patch (debounced per row) ─────────────────────────────── */

  const flushRow = useCallback(
    async (id: string) => {
      const fields = pendingByRow.current.get(id);
      if (!fields || Object.keys(fields).length === 0) return;
      pendingByRow.current.delete(id);
      const snapshot = revertByRow.current.get(id) ?? {};
      revertByRow.current.delete(id);

      abortByRow.current.get(id)?.abort();
      const controller = new AbortController();
      abortByRow.current.set(id, controller);

      saving();
      try {
        await api.put(`${baseUrl}/${id}`, fields, { signal: controller.signal });
        saved();
      } catch (err) {
        if ((err as Error).name === "AbortError") return;
        // Revert each changed field on this row to its pre-edit value
        setItems((prev) =>
          prev.map((i) => (i.id === id ? { ...i, ...snapshot } : i)),
        );
        saveFailed();
      } finally {
        if (abortByRow.current.get(id) === controller) {
          abortByRow.current.delete(id);
        }
      }
    },
    [baseUrl, saving, saved, saveFailed],
  );

  const patch = useCallback(
    (id: string, field: string, value: unknown) => {
      // Optimistic UI update — and capture original value for revert (once per
      // field, on the first patch since the last successful flush).
      setItems((prev) =>
        prev.map((i) => {
          if (i.id !== id) return i;
          const original = revertByRow.current.get(id) ?? {};
          if (!(field in original)) {
            revertByRow.current.set(id, {
              ...original,
              [field]: (i as Record<string, unknown>)[field],
            });
          }
          return { ...i, [field]: value };
        }),
      );
      const pending = pendingByRow.current.get(id) ?? {};
      pending[field] = value;
      pendingByRow.current.set(id, pending);

      const existing = timerByRow.current.get(id);
      if (existing) clearTimeout(existing);
      timerByRow.current.set(
        id,
        setTimeout(() => {
          timerByRow.current.delete(id);
          flushRow(id);
        }, SAVE_DEBOUNCE_MS),
      );
    },
    [flushRow],
  );

  /* ── Remove (optimistic) ───────────────────────────────────── */

  const remove = useCallback(
    async (id: string) => {
      // Cancel any pending edits for this row
      const t = timerByRow.current.get(id);
      if (t) clearTimeout(t);
      timerByRow.current.delete(id);
      pendingByRow.current.delete(id);
      revertByRow.current.delete(id);
      abortByRow.current.get(id)?.abort();
      abortByRow.current.delete(id);

      // Capture snapshot for rollback
      let snapshot: T[] = [];
      setItems((prev) => {
        snapshot = prev;
        return prev.filter((i) => i.id !== id);
      });
      saving();
      try {
        await api.delete(`${baseUrl}/${id}`);
        saved();
      } catch {
        // Restore removed item
        setItems(snapshot);
        saveFailed();
      }
    },
    [baseUrl, saving, saved, saveFailed],
  );

  // Flush any pending row edits on unmount
  useEffect(() => {
    const timers = timerByRow.current;
    const pending = pendingByRow.current;
    return () => {
      for (const [id, t] of timers) {
        clearTimeout(t);
        if (pending.has(id)) flushRow(id);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { items, setItems, add, patch, remove };
}
