"use client";

import { useState, useEffect } from "react";
import type { FilterOptions } from "@/types";

const EMPTY: FilterOptions = {
  divisions: [],
  factories: [],
  categories: [],
  pmos: [],
  pms: [],
  owners: [],
  sponsors: [],
};

/**
 * Fetches filter dropdown options once on mount.
 * Returns a stable object that never changes after the initial load,
 * so dropdowns always show the full set of options regardless of
 * which filters are currently active.
 */
export function useFilterOptions() {
  const [options, setOptions] = useState<FilterOptions>(EMPTY);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    fetch("/api/filter-options")
      .then((res) => {
        if (!res.ok) throw new Error("Failed to fetch filter options");
        return res.json();
      })
      .then((data: FilterOptions) => {
        if (!cancelled) setOptions(data);
      })
      .catch(() => {
        // Silently fall back to empty — selectors just won't show
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return { options, loading };
}
