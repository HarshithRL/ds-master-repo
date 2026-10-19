"use client";

import { useMemo } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ArrowRight, List } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useProjects } from "@/hooks/use-projects";
import { useFilterOptions } from "@/hooks/use-filter-options";
import { useUrlFilters } from "@/hooks/use-url-filters";
import { computePortfolio } from "@/lib/compute-portfolio";
import { PageHeader } from "@/components/layout/page-header";
import { UnifiedFilterBar, ALL_FILTER_FIELDS } from "@/components/ui/unified-filter-bar";
import { HeroKPIStrip } from "./hero-kpi-strip";
import { BudgetAdherence } from "./budget-adherence";
import { ScheduleAdherence } from "./schedule-adherence";
import { BudgetPerformance } from "./budget-performance";
import { CpiSpiChart } from "./cpi-spi-chart";
import { RiskExposureChart } from "./risk-exposure-chart";
import { SchedulePerformance } from "./schedule-performance";
import { PortfolioDistribution } from "./portfolio-distribution";

export function ExecutiveDashboard() {
  const { filters, setFilters } = useUrlFilters();
  const { projects, loading } = useProjects(undefined, {
    externalFilters: filters,
    onFiltersChange: setFilters,
  });
  const { options: filterOptions, loading: optionsLoading } = useFilterOptions();

  const portfolio = useMemo(
    () => (projects.length > 0 ? computePortfolio(projects) : null),
    [projects],
  );

  // Forward the dashboard's current filters to /projects by passing the
  // raw URL search string through — both pages parse the same schema via
  // useUrlFilters, so the table opens already filtered to the same set.
  const searchParams = useSearchParams();
  const projectsHref = useMemo(() => {
    const qs = searchParams.toString();
    return qs ? `/projects?${qs}` : "/projects";
  }, [searchParams]);
  const matchCount = portfolio?.totalProjects ?? 0;

  return (
    <div className="space-y-4 sm:space-y-6 animate-page-enter">
      <PageHeader
        title="Executive Dashboard"
        subtitle={
          !loading && portfolio
            ? `${portfolio.totalProjects} active projects across the portfolio`
            : undefined
        }
      >
        <Button
          asChild
          variant="outline"
          size="sm"
          disabled={loading || matchCount === 0}
        >
          <Link
            href={projectsHref}
            aria-label={`Open ${matchCount} matching project${matchCount === 1 ? "" : "s"} in projects list`}
          >
            <List size={14} className="mr-1.5" />
            View {!loading && portfolio ? `${matchCount} ` : ""}
            {matchCount === 1 ? "project" : "projects"}
            <ArrowRight size={12} className="ml-1.5 opacity-60" />
          </Link>
        </Button>
      </PageHeader>

      {/* Filters — sticky on scroll. Negative top + matching inner padding
          pulls the wrapper up so the filter card pins flush against the
          navbar bottom (the overflow into navbar area sits behind nav's
          z-40). Solid background + bottom border keeps scrolled content
          from bleeding through. */}
      <div className="sticky -top-3 sm:-top-4 lg:-top-6 z-20 -mx-3 px-3 sm:-mx-4 sm:px-4 lg:-mx-6 lg:px-6 pt-3 sm:pt-4 lg:pt-6 pb-2 bg-white dark:bg-[#1A1D23] border-b border-(--border)">
        <UnifiedFilterBar
          filters={filters}
          onChange={setFilters}
          fields={ALL_FILTER_FIELDS}
          filterOptions={filterOptions}
          optionsLoading={optionsLoading}
        />
      </div>

      {/* 1. Hero KPIs */}
      <HeroKPIStrip
        portfolio={portfolio}
        projects={projects}
        loading={loading}
        filters={filters}
        onFiltersChange={setFilters}
      />

      {/* 2. Portfolio distribution — clickable filters */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4">
        <PortfolioDistribution
          variant="gate"
          title="By Gate"
          data={portfolio?.byGate ?? []}
          totalProjects={portfolio?.totalProjects}
          loading={loading}
        />
        <PortfolioDistribution
          variant="tier"
          title="By Tier"
          data={portfolio?.byTier ?? []}
          totalProjects={portfolio?.totalProjects}
          loading={loading}
          filters={filters}
          onFiltersChange={setFilters}
        />
        <PortfolioDistribution
          variant="division"
          title="By Division"
          data={portfolio?.byDivision ?? []}
          totalProjects={portfolio?.totalProjects}
          loading={loading}
          filters={filters}
          onFiltersChange={setFilters}
        />
      </div>

      {/* 3. Adherence pair — budget + schedule */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
        <BudgetAdherence projects={projects} />
        <ScheduleAdherence projects={projects} />
      </div>

      {/* 4. Budget Performance + Schedule Performance */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
        <BudgetPerformance portfolio={portfolio} projects={projects} loading={loading} />
        <SchedulePerformance projects={projects} loading={loading} />
      </div>

      {/* 5. EVM scatter pair — performance vs risk exposure */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
        <CpiSpiChart projects={projects} />
        <RiskExposureChart projects={projects} />
      </div>
    </div>
  );
}
