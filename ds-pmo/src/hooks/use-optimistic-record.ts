"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { api } from "@/lib/api";
import { useSaveStatus, SAVE_DEBOUNCE_MS } from "@/hooks/use-save-status";

/**
 * Optimistic single-record updates with debounced saves + auto-revert on failure.
 *
 * Similar to `useOptimisticList` but for a single record (e.g. budget).
 * - `patch(field, value)` applies the change optimistically, then schedules a
 *   debounced PUT. Multiple field changes within the debounce window are
 *   batched into one request.
 * - On failure, each changed field is reverted to its pre-edit value.
 */
export function useOptimisticRecord<T extends Record<string, unknown>>(opts: {
  /** Initial record from the parent (server data). */
  initial: T | null;
  /** API URL for PUT requests, e.g. `/api/projects/123/budget`. */
  url: string;
}) {
  const { initial, url } = opts;
  const [record, setRecord] = useState<T | null>(initial);
  const { saving, saved, saveFailed } = useSaveStatus();

  // Accumulates pending field changes between flushes
  const pendingFields = useRef<Record<string, unknown>>({});
  // Pre-edit snapshot for revert — captured once per field, on first patch
  // since the last successful flush.
  const revertSnapshot = useRef<Record<string, unknown>>({});
  const flushTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => setRecord(initial), [initial]);

  const flush = useCallback(async () => {
    const fields = pendingFields.current;
    if (Object.keys(fields).length === 0) return;
    pendingFields.current = {};
    const snapshot = revertSnapshot.current;
    revertSnapshot.current = {};

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    saving();
    try {
      await api.put(url, fields, { signal: controller.signal });
      saved();
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      // Revert each changed field to its pre-edit value
      setRecord((prev) => (prev ? { ...prev, ...snapshot } : prev));
      saveFailed();
    }
  }, [url, saving, saved, saveFailed]);

  const patch = useCallback(
    (field: string, value: unknown) => {
      // Optimistic UI update
      setRecord((prev) => {
        if (!prev) return prev;
        // Capture the original value once per field (don't overwrite if the
        // user types again in the same field before the flush).
        if (!(field in revertSnapshot.current)) {
          revertSnapshot.current[field] = prev[field];
        }
        return { ...prev, [field]: value };
      });
      pendingFields.current[field] = value;

      clearTimeout(flushTimer.current);
      flushTimer.current = setTimeout(flush, SAVE_DEBOUNCE_MS);
    },
    [flush],
  );

  // Flush any pending changes on unmount so quick navigations don't lose edits
  useEffect(() => {
    return () => {
      if (Object.keys(pendingFields.current).length > 0) {
        clearTimeout(flushTimer.current);
        flush();
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { record, setRecord, patch };
}
