"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Plus } from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { UnifiedFilterBar, ALL_FILTER_FIELDS } from "@/components/ui/unified-filter-bar";
import { ProjectTable } from "@/components/dashboard/project-table";
import { Pagination } from "@/components/ui/pagination";
import { useProjects } from "@/hooks/use-projects";
import { useFilterOptions } from "@/hooks/use-filter-options";
import { useUrlFilters } from "@/hooks/use-url-filters";

export function ProjectsList() {
  // Read filters from the URL so deep-links from the dashboard land with
  // the same filter set applied; writes flow back to the URL via setFilters.
  const { filters: urlFilters, setFilters: setUrlFilters } = useUrlFilters();
  const {
    projects,
    total,
    summary,
    loading,
    filters,
    setFilters,
    page,
    pageSize,
    setPage,
    setPageSize,
  } = useProjects(undefined, {
    pagination: { initialPageSize: 25 },
    externalFilters: urlFilters,
    onFiltersChange: setUrlFilters,
  });
  const { options: filterOptions, loading: optionsLoading } = useFilterOptions();

  return (
    <div className="flex-1 min-h-0 flex flex-col gap-4">
      <PageHeader
        title="Projects"
        subtitle={`${total.toLocaleString()} project${total !== 1 ? "s" : ""}`}
      >
        <Button asChild className="bg-etex-orange hover:bg-etex-orange/90 text-white">
          <Link href="/projects/new">
            <Plus size={16} className="mr-1.5" /> New Project
          </Link>
        </Button>
      </PageHeader>

      <UnifiedFilterBar
        filters={filters}
        onChange={setFilters}
        fields={ALL_FILTER_FIELDS}
        filterOptions={filterOptions}
        optionsLoading={optionsLoading}
      />

      <ProjectTable
        projects={projects}
        loading={loading}
        summary={summary}
        sortBy={filters.sortBy}
        sortDir={filters.sortDir}
        onSortChange={(sortBy, sortDir) => setFilters({ ...filters, sortBy, sortDir })}
      />

      <Pagination
        page={page}
        pageSize={pageSize}
        total={total}
        onPageChange={setPage}
        onPageSizeChange={(s) => {
          setPageSize(s);
          setPage(1);
        }}
        unit="projects"
        loading={loading}
      />
    </div>
  );
}
