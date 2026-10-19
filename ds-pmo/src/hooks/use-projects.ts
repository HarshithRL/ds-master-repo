"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import type { ProjectListItem, DashboardFilters } from "@/types";
import type {
  Financials,
  SchedulePerf,
  RiskAggregates,
  IssueAggregates,
  ScopeChangeAggregates,
} from "@/lib/project-table-metrics";

export interface SummaryBucket {
  count: number;
  financials: Financials;
  schedulePerf: SchedulePerf;
  riskAggregates: RiskAggregates;
  issueAggregates: IssueAggregates;
  scopeAggregates: ScopeChangeAggregates;
  pctGate: number;
}

export interface ProjectsSummary {
  execution: SummaryBucket;
  development: SummaryBucket;
}

interface PaginatedResponse {
  items: ProjectListItem[];
  total: number;
  page: number;
  pageSize: number;
  summary: ProjectsSummary;
}

interface UseProjectsOpts {
  externalFilters?: DashboardFilters;
  onFiltersChange?: (f: DashboardFilters) => void;
  /** Enable server-side pagination. When set, hook returns total/summary and exposes page controls. */
  pagination?: { initialPage?: number; initialPageSize?: number };
}

/**
 * Fetch projects with optional server-side pagination.
 *
 * Pagination mode (opts.pagination provided):
 *  - Sends `page` + `pageSize` query params, parses the envelope response,
 *    exposes `total`, `page`, `pageSize`, `summary`, plus `setPage`/`setPageSize`.
 *  - Page auto-resets to 1 whenever filters change.
 *
 * Non-paginated mode (backward compatible): returns the full filtered list.
 */
export function useProjects(initialFilters?: DashboardFilters, opts?: UseProjectsOpts) {
  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [summary, setSummary] = useState<ProjectsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [internalFilters, setInternalFilters] = useState<DashboardFilters>(initialFilters || {});
  const filters = opts?.externalFilters ?? internalFilters;
  const setFilters = opts?.onFiltersChange ?? setInternalFilters;

  const paginated = !!opts?.pagination;
  const [page, setPage] = useState(opts?.pagination?.initialPage ?? 1);
  const [pageSize, setPageSize] = useState(opts?.pagination?.initialPageSize ?? 25);

  // Reset to first page whenever filters change in paginated mode.
  const filtersKey = JSON.stringify(filters);
  const lastFiltersKey = useRef(filtersKey);
  useEffect(() => {
    if (paginated && lastFiltersKey.current !== filtersKey) {
      lastFiltersKey.current = filtersKey;
      setPage(1);
    }
  }, [filtersKey, paginated]);

  const fetchProjects = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (filters.search) params.set("search", filters.search);
      if (filters.lifecycle) params.set("lifecycle", filters.lifecycle);
      if (filters.phase?.length) params.set("phase", filters.phase.join(","));
      if (filters.tier?.length) params.set("tier", filters.tier.join(","));
      if (filters.factory?.length) params.set("factory", filters.factory.join(","));
      if (filters.division?.length) params.set("division", filters.division.join(","));
      if (filters.category?.length) params.set("category", filters.category.join(","));
      if (filters.pmo?.length) params.set("pmo", filters.pmo.join(","));
      if (filters.pm?.length) params.set("pm", filters.pm.join(","));
      if (filters.owner?.length) params.set("owner", filters.owner.join(","));
      if (filters.sponsor?.length) params.set("sponsor", filters.sponsor.join(","));
      if (filters.status?.length) params.set("status", filters.status.join(","));
      if (filters.msrOnly) params.set("msrOnly", "true");
      if (filters.excomOnly) params.set("excomOnly", "true");
      if (filters.sortBy) params.set("sortBy", filters.sortBy);
      if (filters.sortDir) params.set("sortDir", filters.sortDir);
      if (paginated) {
        params.set("page", String(page));
        params.set("pageSize", String(pageSize));
      }

      const res = await fetch(`/api/projects?${params.toString()}`);
      if (!res.ok) throw new Error("Failed to fetch projects");
      const data = await res.json();

      if (paginated) {
        const env = data as PaginatedResponse;
        setProjects(env.items);
        setTotal(env.total);
        setSummary(env.summary);
      } else {
        const list = data as ProjectListItem[];
        setProjects(list);
        setTotal(list.length);
        setSummary(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
      setProjects([]);
      setTotal(0);
      setSummary(null);
    } finally {
      setLoading(false);
    }
  }, [filters, paginated, page, pageSize]);

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  return {
    projects,
    total,
    summary,
    loading,
    error,
    filters,
    setFilters,
    page,
    pageSize,
    setPage,
    setPageSize,
    refetch: fetchProjects,
  };
}
