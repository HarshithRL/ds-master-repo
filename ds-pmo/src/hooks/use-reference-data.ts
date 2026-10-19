import { useEffect, useSyncExternalStore } from "react";
import { api } from "@/lib/api";

/**
 * Lightweight types for selector dropdowns.
 * These match the lean `/api/factories` and `/api/categories` responses
 * (no _count, no division relation — just what selectors need).
 */
export interface FactoryOption {
  id: string;
  name: string;
  code: string | null;
  shortName: string | null;
  country: string | null;
  currency: string | null;
  divisionId: string | null;
}

export interface CategoryOption {
  id: string;
  name: string;
  code: string;
}

export interface ReferenceData {
  factories: FactoryOption[];
  categories: CategoryOption[];
}

/* ── Module-level store (survives across navigations) ──────────── */

const TTL = 12 * 60 * 60 * 1000; // 12 hours

const EMPTY: ReferenceData = { factories: [], categories: [] };

// Single source of truth: a stable `ReferenceData` reference that's replaced
// (not mutated) whenever the data changes, plus a freshness timestamp.
let snapshot: ReferenceData = EMPTY;
let ts = 0;
const subscribers = new Set<() => void>();

function setSnapshot(next: ReferenceData) {
  snapshot = next;
  ts = Date.now();
  subscribers.forEach((cb) => cb());
}

function subscribe(cb: () => void): () => void {
  subscribers.add(cb);
  return () => {
    subscribers.delete(cb);
  };
}

function getSnapshot(): ReferenceData {
  return snapshot;
}

// Deduplicates concurrent fetches — only one in-flight request at a time
let inflight: Promise<ReferenceData> | null = null;

function fetchReferenceData(): Promise<ReferenceData> {
  if (!inflight) {
    inflight = Promise.all([
      api.get<FactoryOption[]>("/api/factories").catch(() => [] as FactoryOption[]),
      api.get<CategoryOption[]>("/api/categories").catch(() => [] as CategoryOption[]),
    ])
      .then(([factories, categories]) => {
        const next: ReferenceData = { factories, categories };
        setSnapshot(next);
        inflight = null;
        return next;
      })
      .catch((err) => {
        inflight = null;
        throw err;
      });
  }
  return inflight;
}

/** Force-refresh on next access (call after admin CRUD mutations). */
export function invalidateReferenceData() {
  ts = 0;
  // Trigger a refresh and let subscribers re-render when it lands.
  fetchReferenceData().catch(() => {});
}

/**
 * Shared hook for factory + category reference data.
 * - 12-hour client-side cache (module-level, survives navigation)
 * - Deduplicates concurrent fetches
 * - useSyncExternalStore keeps every mounted hook in sync with the
 *   module-level snapshot without setState-in-effect cascades.
 */
export function useReferenceData(): ReferenceData {
  const data = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);

  // Background refresh when stale. No state writes here — the fetch calls
  // setSnapshot() on success, which notifies all subscribers via the store.
  useEffect(() => {
    if (Date.now() - ts >= TTL) {
      fetchReferenceData().catch(() => {});
    }
  }, []);

  return data;
}
