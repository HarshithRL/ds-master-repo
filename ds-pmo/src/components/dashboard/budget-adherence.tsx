"use client";

import { useMemo, useState, memo, useCallback } from "react";
import Link from "next/link";
import { formatCurrency, cn } from "@/lib/utils";
import { calcEAC, calcVariance, calcVariancePct } from "@/lib/calculations";
import { ExpandableWidget } from "./expandable-widget";
import type { ProjectListItem } from "@/types";

interface BudgetAdherenceProps {
  projects: ProjectListItem[];
}

/* McKinsey-style diverging palette — muted, boardroom-grade */
const BUCKETS = [
  { key: "under2", label: "> 2% Underrun", bg: "#1B7A6E" },
  { key: "under0", label: "0–2% Underrun", bg: "#6DAFA7" },
  { key: "over0",  label: "0–2% Overrun",  bg: "#C4A35A" },
  { key: "over2",  label: "2–5% Overrun",  bg: "#D4804E" },
  { key: "over5",  label: "> 5% Overrun",  bg: "#B83A3A" },
] as const;

type BucketKey = (typeof BUCKETS)[number]["key"];

const DEFAULT_BUCKET: BucketKey = "over0";
const BASE_H = 28;
const HOVER_H = 34;

function getBucketKey(variancePct: number): BucketKey {
  // VAC sign: positive = under budget, negative = over budget.
  if (variancePct > 2) return "under2";
  if (variancePct >= 0) return "under0";
  if (variancePct >= -2) return "over0";
  if (variancePct >= -5) return "over2";
  return "over5";
}

export const BudgetAdherence = memo(function BudgetAdherence({ projects }: BudgetAdherenceProps) {
  const [lockedBucket, setLockedBucket] = useState<BucketKey>(DEFAULT_BUCKET);
  const [hoveredBucket, setHoveredBucket] = useState<BucketKey | null>(null);
  const [showAll, setShowAll] = useState(false);

  // The visible bucket is hover if hovering, otherwise locked
  const visibleBucket = hoveredBucket ?? lockedBucket;

  const handleClick = useCallback((key: BucketKey) => {
    setLockedBucket(key);
  }, []);

  const { buckets, projectsByBucket } = useMemo(() => {
    const b: Record<BucketKey, number> = {
      under2: 0, under0: 0, over0: 0, over2: 0, over5: 0,
    };
    const byBucket: Record<BucketKey, (ProjectListItem & { variancePct: number; variance: number })[]> = {
      under2: [], under0: [], over0: [], over2: [], over5: [],
    };

    const withBudget = projects.filter(
      (p) => p.budget && p.budget.bac > 0 && calcEAC(p.budget) > 0,
    );

    withBudget.forEach((p) => {
      const variance = calcVariance(p.budget!);
      const variancePct = calcVariancePct(p.budget!);
      const key = getBucketKey(variancePct);
      b[key]++;
      byBucket[key].push({ ...p, variancePct, variance });
    });

    for (const key of Object.keys(byBucket) as BucketKey[]) {
      // Ascending so most-overrun (most negative) appears first in overrun
      // buckets; mirrors the original "biggest overrun first" UX after the
      // VAC sign flip (positive = under budget).
      byBucket[key].sort((a, b) => a.variancePct - b.variancePct);
    }

    return { buckets: b, projectsByBucket: byBucket };
  }, [projects]);

  const total = Object.values(buckets).reduce((s, v) => s + v, 0);
  const allBucketProjects = projectsByBucket[visibleBucket];
  const activeProjects = showAll ? allBucketProjects : allBucketProjects.slice(0, 5);
  const activeMeta = BUCKETS.find((b) => b.key === visibleBucket)!;

  return (
    <ExpandableWidget title="Budget Adherence">
      <div className="px-5 pb-5 pt-4 space-y-4">
        {total > 0 ? (
          <>
            {/* Stacked bar — continuous, selected segment is taller (centered) */}
            <div className="relative flex items-center h-9">
              {BUCKETS.map((bucket) => {
                const count = buckets[bucket.key];
                if (count === 0) return null;
                const width = (count / total) * 100;
                const isHovered = hoveredBucket === bucket.key;
                const isLocked = lockedBucket === bucket.key;
                const isActive = isHovered || (hoveredBucket === null && isLocked);
                return (
                  <div
                    key={bucket.key}
                    className="flex items-center justify-center text-[10px] font-bold text-white cursor-pointer transition-all duration-200"
                    style={{
                      width: `${width}%`,
                      height: isActive ? HOVER_H : BASE_H,
                      backgroundColor: bucket.bg,
                      opacity: isActive ? 1 : 0.4,
                    }}
                    onMouseEnter={() => setHoveredBucket(bucket.key)}
                    onMouseLeave={() => setHoveredBucket(null)}
                    onClick={() => handleClick(bucket.key)}
                  >
                    {width > 8 ? count : ""}
                  </div>
                );
              })}
            </div>

            {/* Legend */}
            <div className="flex flex-wrap gap-x-4 gap-y-1.5">
              {BUCKETS.map((bucket) => {
                const isVisible = visibleBucket === bucket.key;
                const isLocked = lockedBucket === bucket.key;
                return (
                  <div
                    key={bucket.key}
                    className={cn(
                      "flex items-center gap-1.5 cursor-pointer rounded px-1.5 py-0.5 -mx-1 transition-all duration-150",
                      isVisible
                        ? "bg-etex-gray-100 dark:bg-[#282C34]"
                        : "opacity-50 hover:opacity-80",
                    )}
                    onMouseEnter={() => setHoveredBucket(bucket.key)}
                    onMouseLeave={() => setHoveredBucket(null)}
                    onClick={() => handleClick(bucket.key)}
                  >
                    <span
                      className={cn("w-2.5 h-2.5 rounded-sm shrink-0", isLocked && "ring-1 ring-etex-gray-700 dark:ring-gray-300")}
                      style={{ backgroundColor: bucket.bg }}
                    />
                    <span className={cn(
                      "text-[10px] text-etex-gray-500 dark:text-gray-400",
                      isVisible && "text-etex-gray-700 dark:text-gray-300 font-medium",
                    )}>
                      {bucket.label} ({buckets[bucket.key]})
                    </span>
                  </div>
                );
              })}
            </div>

            {/* Active indicator bar */}
            <div
              className="h-0.5 rounded-full transition-colors duration-200"
              style={{ backgroundColor: activeMeta.bg }}
            />

            {/* Project list */}
            <div className={showAll ? "max-h-72 overflow-y-auto" : "h-44"}>
              <div className="flex items-center justify-between mb-2">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-etex-gray-400 dark:text-gray-500">
                  {activeMeta.label} — {showAll ? `All (${allBucketProjects.length})` : "Top 5"}
                </p>
                {allBucketProjects.length > 5 && (
                  <button
                    type="button"
                    onClick={() => setShowAll((v) => !v)}
                    className="text-[10px] font-medium text-etex-orange hover:underline cursor-pointer"
                  >
                    {showAll ? "Show less" : `Show all (${allBucketProjects.length})`}
                  </button>
                )}
              </div>
              {activeProjects.length > 0 ? (
                <div className="space-y-0.5">
                  {activeProjects.map((p) => (
                    <Link
                      key={p.id}
                      href={`/projects/${p.id}`}
                      className="flex items-center justify-between py-2 px-2.5 rounded hover:bg-etex-gray-50 dark:hover:bg-[#282C34] transition-colors"
                    >
                      <span className="text-xs text-etex-gray-700 dark:text-gray-300 truncate mr-3">
                        {p.name}
                      </span>
                      <span
                        className={cn(
                          "text-[11px] font-semibold shrink-0 tabular-nums",
                          p.variance >= 0 ? "text-success" : "text-danger",
                        )}
                      >
                        {formatCurrency(p.variance, { signed: true, compact: true })}
                        {" "}({p.variancePct > 0 ? "+" : ""}{p.variancePct.toFixed(1)}%)
                      </span>
                    </Link>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-etex-gray-300 dark:text-etex-gray-600 pt-6 text-center">
                  No projects in this range
                </p>
              )}
            </div>
          </>
        ) : (
          <p className="text-xs text-etex-gray-400 text-center py-8">No budget data available</p>
        )}
      </div>
    </ExpandableWidget>
  );
});
