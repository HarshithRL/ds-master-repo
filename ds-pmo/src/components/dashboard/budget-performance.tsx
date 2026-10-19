"use client";

import Link from "next/link";
import { formatCurrency, cn } from "@/lib/utils";
import { calcVariance, calcVariancePct } from "@/lib/calculations";
import { Skeleton } from "@/components/ui/skeleton";
import { ExpandableWidget } from "./expandable-widget";
import type { PortfolioSummary, ProjectListItem } from "@/types";
import { useMemo, memo } from "react";

interface BudgetPerformanceProps {
  portfolio: PortfolioSummary | null;
  projects: ProjectListItem[];
  loading?: boolean;
}

interface BarRow {
  label: string;
  sublabel: string;
  value: number;
  color: string;
  colorOver?: string;
  isOver?: boolean;
}

export const BudgetPerformance = memo(function BudgetPerformance({ portfolio, projects, loading }: BudgetPerformanceProps) {
  const overrunProjects = useMemo(() => {
    return projects
      .filter((p) => p.budget && p.budget.bac > 0 && calcVariance(p.budget) < 0)
      .map((p) => ({
        id: p.id,
        name: p.name,
        variance: calcVariance(p.budget!),
        pctOver: calcVariancePct(p.budget!),
      }))
      .sort((a, b) => a.variance - b.variance)
      .slice(0, 5);
  }, [projects]);

  if (loading) {
    return (
      <ExpandableWidget title="Budget Performance">
        <div className="p-4 space-y-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i}>
              <div className="flex items-baseline justify-between mb-1">
                <Skeleton className="h-3 w-24" />
                <Skeleton className="h-3 w-14" />
              </div>
              <Skeleton className="h-5 w-full rounded-sm" />
            </div>
          ))}
        </div>
      </ExpandableWidget>
    );
  }

  if (!portfolio) {
    return (
      <ExpandableWidget title="Budget Performance">
        <div className="p-4 text-xs text-etex-gray-400 text-center py-6">No data</div>
      </ExpandableWidget>
    );
  }

  const { totalBAC, totalEAC, totalActuals, totalCommitted } = portfolio;
  const totalActualsCommitted = totalActuals + totalCommitted;
  const eacOverBudget = totalEAC > totalBAC;

  const rows: BarRow[] = [
    { label: "BAC (Current)", sublabel: "Budget at Completion", value: totalBAC, color: "bg-info" },
    { label: "EAC", sublabel: "Estimate at Completion", value: totalEAC, color: "bg-etex-orange", colorOver: "bg-danger", isOver: eacOverBudget },
    { label: "Actuals + Committed", sublabel: "Costs incurred to date", value: totalActualsCommitted, color: "bg-amber-500" },
    { label: "Actuals", sublabel: "Invoiced to date", value: totalActuals, color: "bg-success" },
  ];

  const maxValue = Math.max(...rows.map((r) => r.value), 1);

  return (
    <ExpandableWidget title="Budget Performance">
      <div className="p-4 space-y-4">
        <div className="space-y-3">
          {rows.map((row) => {
            const width = maxValue > 0 ? (row.value / maxValue) * 100 : 0;
            const barColor = row.isOver && row.colorOver ? row.colorOver : row.color;
            return (
              <div key={row.label}>
                <div className="flex items-baseline justify-between mb-1">
                  <div className="flex items-baseline gap-1.5">
                    <span className="text-xs font-semibold text-etex-gray-700 dark:text-gray-300">{row.label}</span>
                    <span className="text-[10px] text-etex-gray-400 dark:text-gray-500">{row.sublabel}</span>
                  </div>
                  <span className="text-xs font-semibold text-etex-gray-700 dark:text-gray-300">
                    {formatCurrency(row.value, { compact: true })}
                  </span>
                </div>
                <div className="relative h-5 bg-etex-gray-100 dark:bg-[#282C34] rounded-sm overflow-hidden">
                  <div className={cn(barColor, "h-full rounded-sm transition-all duration-500")} style={{ width: `${width}%` }} />
                  {row.label !== "BAC (Current)" && totalBAC > 0 && (
                    <div className="absolute top-0 bottom-0 w-px bg-etex-gray-700 dark:bg-gray-300 opacity-50" style={{ left: `${(totalBAC / maxValue) * 100}%` }} />
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {overrunProjects.length > 0 && (
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-etex-gray-500 dark:text-gray-400 mb-2">Top Overruns</p>
            <div className="space-y-1.5">
              {overrunProjects.map((p) => (
                <Link key={p.id} href={`/projects/${p.id}`} className="flex items-center justify-between py-1 px-2 rounded hover:bg-etex-gray-50 dark:hover:bg-[#282C34] transition-colors">
                  <span className="text-xs text-etex-gray-700 dark:text-gray-300 truncate mr-3">{p.name}</span>
                  <span className="text-xs font-semibold text-danger shrink-0">{formatCurrency(p.variance, { signed: true })} ({Math.round(p.pctOver)}%)</span>
                </Link>
              ))}
            </div>
          </div>
        )}
      </div>
    </ExpandableWidget>
  );
});
