"use client";

import { useCallback, useMemo } from "react";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import type { DashboardFilters } from "@/types";
import { normalizeLifecycleFilter } from "@/lib/lifecycle-filter";

/** Keys that hold comma-separated arrays in the URL */
const ARRAY_KEYS: (keyof DashboardFilters)[] = [
  "phase",
  "tier",
  "factory",
  "division",
  "category",
  "pmo",
  "pm",
  "owner",
  "sponsor",
  "status",
];

/** Parse URL search params into DashboardFilters */
function parseParams(sp: URLSearchParams): DashboardFilters {
  const filters: DashboardFilters = {};

  const search = sp.get("search");
  if (search) filters.search = search;

  const lifecycle = normalizeLifecycleFilter(sp.get("lifecycle"));
  if (lifecycle) filters.lifecycle = lifecycle;

  for (const key of ARRAY_KEYS) {
    const val = sp.get(key);
    if (val) {
      (filters as Record<string, string[]>)[key] = val.split(",").filter(Boolean);
    }
  }

  if (sp.get("msrOnly") === "true") filters.msrOnly = true;
  if (sp.get("excomOnly") === "true") filters.excomOnly = true;
  if (sp.get("sortBy")) filters.sortBy = sp.get("sortBy")!;
  const sortDir = sp.get("sortDir");
  if (sortDir === "asc" || sortDir === "desc") filters.sortDir = sortDir;

  return filters;
}

/** Serialize DashboardFilters to URLSearchParams string */
function serializeFilters(filters: DashboardFilters): string {
  const params = new URLSearchParams();

  if (filters.search) params.set("search", filters.search);
  if (filters.lifecycle) params.set("lifecycle", filters.lifecycle);

  for (const key of ARRAY_KEYS) {
    const arr = filters[key] as string[] | undefined;
    if (arr?.length) params.set(key, arr.join(","));
  }

  if (filters.msrOnly) params.set("msrOnly", "true");
  if (filters.excomOnly) params.set("excomOnly", "true");
  if (filters.sortBy) params.set("sortBy", filters.sortBy);
  if (filters.sortDir) params.set("sortDir", filters.sortDir);

  return params.toString();
}

/**
 * Two-way sync between DashboardFilters and URL search params.
 * Reading: parses current URL into filters.
 * Writing: updates URL (shallow, no navigation) when filters change.
 */
export function useUrlFilters() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const filters = useMemo(() => parseParams(searchParams), [searchParams]);

  const setFilters = useCallback(
    (next: DashboardFilters) => {
      const qs = serializeFilters(next);
      const url = qs ? `${pathname}?${qs}` : pathname;
      router.replace(url, { scroll: false });
    },
    [pathname, router],
  );

  return { filters, setFilters };
}
