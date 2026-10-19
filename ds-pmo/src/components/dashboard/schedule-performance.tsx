"use client";

import Link from "next/link";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { ExpandableWidget } from "./expandable-widget";
import type { ProjectListItem } from "@/types";
import { useMemo, memo } from "react";

interface SchedulePerformanceProps {
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

export const SchedulePerformance = memo(function SchedulePerformance({
  projects,
  loading,
}: SchedulePerformanceProps) {
  const stats = useMemo(() => {
    const withSchedule = projects.filter((p) => p.scheduleBuffer != null);
    const delayed = withSchedule.filter((p) => p.scheduleBuffer! < 0);
    const onTime = withSchedule.filter((p) => p.scheduleBuffer! >= 0);

    const avgBuffer =
      withSchedule.length > 0
        ? Math.round(
            withSchedule.reduce((s, p) => s + p.scheduleBuffer!, 0) /
              withSchedule.length,
          )
        : 0;

    const avgDelay =
      delayed.length > 0
        ? Math.round(
            delayed.reduce((s, p) => s + Math.abs(p.scheduleBuffer!), 0) /
              delayed.length,
          )
        : 0;

    const maxDelay =
      delayed.length > 0
        ? Math.max(...delayed.map((p) => Math.abs(p.scheduleBuffer!)))
        : 0;

    const avgAhead =
      onTime.length > 0
        ? Math.round(
            onTime.reduce((s, p) => s + p.scheduleBuffer!, 0) / onTime.length,
          )
        : 0;

    return {
      totalTracked: withSchedule.length,
      onTimeCount: onTime.length,
      delayedCount: delayed.length,
      avgBuffer,
      avgDelay,
      maxDelay,
      avgAhead,
    };
  }, [projects]);

  const mostDelayed = useMemo(() => {
    return projects
      .filter((p) => p.scheduleBuffer != null && p.scheduleBuffer < 0)
      .sort((a, b) => (a.scheduleBuffer ?? 0) - (b.scheduleBuffer ?? 0))
      .slice(0, 5);
  }, [projects]);

  if (loading) {
    return (
      <ExpandableWidget title="Schedule Performance">
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

  if (stats.totalTracked === 0) {
    return (
      <ExpandableWidget title="Schedule Performance">
        <div className="p-4 text-xs text-etex-gray-400 text-center py-6">
          No schedule data available
        </div>
      </ExpandableWidget>
    );
  }

  const rows: BarRow[] = [
    {
      label: "Avg. Buffer",
      sublabel: "Across all tracked projects",
      value: stats.avgBuffer,
      color: "bg-info",
      colorOver: "bg-danger",
      isOver: stats.avgBuffer < 0,
    },
    {
      label: "Avg. Ahead",
      sublabel: `${stats.onTimeCount} on-time projects`,
      value: stats.avgAhead,
      color: "bg-success",
    },
    {
      label: "Avg. Delay",
      sublabel: `${stats.delayedCount} delayed projects`,
      value: stats.avgDelay,
      color: "bg-etex-orange",
      colorOver: "bg-danger",
      isOver: stats.avgDelay > 30,
    },
    {
      label: "Max Delay",
      sublabel: "Worst performing project",
      value: stats.maxDelay,
      color: "bg-amber-500",
      colorOver: "bg-danger",
      isOver: stats.maxDelay > 60,
    },
  ];

  const maxValue = Math.max(...rows.map((r) => Math.abs(r.value)), 1);

  return (
    <ExpandableWidget title="Schedule Performance">
      <div className="p-4 space-y-4">
        <div className="space-y-3">
          {rows.map((row) => {
            const absVal = Math.abs(row.value);
            const width = maxValue > 0 ? (absVal / maxValue) * 100 : 0;
            const barColor =
              row.isOver && row.colorOver ? row.colorOver : row.color;
            return (
              <div key={row.label}>
                <div className="flex items-baseline justify-between mb-1">
                  <div className="flex items-baseline gap-1.5">
                    <span className="text-xs font-semibold text-etex-gray-700 dark:text-gray-300">
                      {row.label}
                    </span>
                    <span className="text-[10px] text-etex-gray-400 dark:text-gray-500">
                      {row.sublabel}
                    </span>
                  </div>
                  <span
                    className={cn(
                      "text-xs font-semibold tabular-nums",
                      row.isOver
                        ? "text-danger"
                        : "text-etex-gray-700 dark:text-gray-300",
                    )}
                  >
                    {row.value < 0 ? "" : ""}
                    {row.value}d
                  </span>
                </div>
                <div className="relative h-5 bg-etex-gray-100 dark:bg-[#282C34] rounded-sm overflow-hidden">
                  <div
                    className={cn(
                      barColor,
                      "h-full rounded-sm transition-all duration-500",
                    )}
                    style={{ width: `${width}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>

        {mostDelayed.length > 0 && (
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-etex-gray-500 dark:text-gray-400 mb-2">
              Most Delayed
            </p>
            <div className="space-y-1.5">
              {mostDelayed.map((p) => (
                <Link
                  key={p.id}
                  href={`/projects/${p.id}`}
                  className="flex items-center justify-between py-1 px-2 rounded hover:bg-etex-gray-50 dark:hover:bg-[#282C34] transition-colors"
                >
                  <span className="text-xs text-etex-gray-700 dark:text-gray-300 truncate mr-3">
                    {p.name}
                  </span>
                  <span className="text-xs font-semibold text-danger shrink-0 tabular-nums">
                    {p.scheduleBuffer}d
                  </span>
                </Link>
              ))}
            </div>
          </div>
        )}
      </div>
    </ExpandableWidget>
  );
});
