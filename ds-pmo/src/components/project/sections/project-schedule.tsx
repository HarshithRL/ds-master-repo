"use client";

import { AutoDateInput, AutoMetric, RowLabel } from "@/components/ui/auto-fields";
import { PhaseGateTimeline } from "@/components/project/phase-gate-timeline";
import { GatesTab } from "@/components/project/tabs/gates-tab";
import { MilestonesTab } from "@/components/project/tabs/milestones-tab";
import { cn } from "@/lib/utils";
import { calcScheduleBufferDays } from "@/lib/calculations";
import { computeDaysGreenToWhite } from "@/lib/progress";
import type { ProjectWithRelations } from "@/types";

/* ── Display helpers — all derived, no stored values ──────────────── */

/** Signed `+N d` / `−N d` value with sentiment color. */
function BufferValue({ days }: { days: number | null }) {
  if (days == null) {
    return <span className="text-sm text-muted-foreground font-mono">&mdash;</span>;
  }
  const color = days < 0 ? "text-danger" : days > 0 ? "text-success" : "text-muted-foreground";
  return (
    <span className={cn("text-sm font-semibold font-mono tabular-nums", color)}>
      {days > 0 ? "+" : ""}{days}d
    </span>
  );
}

/** Previous-month buffer with trend arrow vs current. */
function BufferPrevValue({
  prev,
  current,
}: {
  prev: number | null | undefined;
  current: number | null;
}) {
  if (prev == null) {
    return <span className="text-sm text-muted-foreground font-mono">&mdash;</span>;
  }
  const delta = current != null ? current - prev : 0;
  const showArrow = Math.abs(delta) >= 1;
  const improving = delta > 0;
  const color = prev < 0 ? "text-danger" : prev > 0 ? "text-success" : "text-muted-foreground";
  return (
    <span className={cn("inline-flex items-center gap-1 text-sm font-semibold font-mono tabular-nums", color)}>
      {prev > 0 ? "+" : ""}{prev}d
      {showArrow && (
        <span className={cn("text-[10px]", improving ? "text-success" : "text-danger")}>
          {improving ? "↑" : "↓"}
        </span>
      )}
    </span>
  );
}

/* ── Main Component ──────────────────────────────────────────────── */

interface ProjectScheduleProps {
  project: ProjectWithRelations;
  projectId: string;
  patch: (fields: Record<string, unknown>) => void;
  latestSnapshot: { varianceAtCompletion: number | null; scheduleBuffer: number | null; periodLabel: string } | null;
  hoveredGate: string | null;
  onTimelineMouseOver: (e: React.MouseEvent) => void;
  onTimelineMouseLeave: () => void;
  onGateHover: (gateKey: string | null) => void;
}

export function ProjectSchedule({
  project,
  projectId,
  patch,
  latestSnapshot,
  hoveredGate,
  onTimelineMouseOver,
  onTimelineMouseLeave,
  onGateHover,
}: ProjectScheduleProps) {
  const scheduleBuffer = calcScheduleBufferDays(
    project.plannedCompletionDate,
    project.expectedCompletionDate,
  );
  const daysGreenToWhite = computeDaysGreenToWhite(project.gates ?? []);

  return (
    <>
      {/* ── Inputs ─────────────────────────────────────────────────
          Three logical column groups stacked vertically: schedule dates,
          open-item counters, and float metrics. Each column has its own
          mini-header so the relationship between fields stays obvious. */}
      <div className="rounded-md border border-border bg-card">
        <div className="px-4 py-2 border-b border-border text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
          Inputs
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 divide-y sm:divide-y-0 sm:divide-x divide-border">
          {/* Dates */}
          <div>
            <div className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70 bg-muted/30 border-b border-border">
              Dates
            </div>
            <div className="divide-y divide-border/60">
              <div className="grid grid-cols-[1fr_140px] items-center gap-3 px-3 py-2">
                <RowLabel hint="Real start date of project execution. Backfilled from the RED gate completion date for existing projects.">Actual Start</RowLabel>
                <AutoDateInput value={project.actualStartDate} onSave={(v) => patch({ actualStartDate: v })} />
              </div>
              <div className="grid grid-cols-[1fr_140px] items-center gap-3 px-3 py-2">
                <RowLabel hint="Original target date from the approved business case">Planned Completion</RowLabel>
                <AutoDateInput value={project.plannedCompletionDate} onSave={(v) => patch({ plannedCompletionDate: v })} />
              </div>
              <div className="grid grid-cols-[1fr_140px] items-center gap-3 px-3 py-2">
                <RowLabel hint="Current realistic forecast for project completion">Expected Completion</RowLabel>
                <AutoDateInput value={project.expectedCompletionDate} onSave={(v) => patch({ expectedCompletionDate: v })} />
              </div>
            </div>
          </div>

          {/* Open items */}
          <div>
            <div className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70 bg-muted/30 border-b border-border">
              Open Items
            </div>
            <div className="divide-y divide-border/60">
              <div className="grid grid-cols-[1fr_140px] items-center gap-3 px-3 py-2">
                <RowLabel hint="Number of RIDs (Review Item Discrepancies) currently open">RIDs Open</RowLabel>
                <AutoMetric
                  value={project.ridsOpen ?? null}
                  onSave={(v) => patch({ ridsOpen: v !== null ? Math.round(v) : null })}
                  unit=""
                  integer
                />
              </div>
              <div className="grid grid-cols-[1fr_140px] items-center gap-3 px-3 py-2">
                <RowLabel hint="Number of red flags currently open">Red Flags Open</RowLabel>
                <AutoMetric
                  value={project.redFlagsOpen ?? null}
                  onSave={(v) => patch({ redFlagsOpen: v !== null ? Math.round(v) : null })}
                  unit=""
                  integer
                />
              </div>
            </div>
          </div>

          {/* Float metrics */}
          <div>
            <div className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70 bg-muted/30 border-b border-border">
              Float
            </div>
            <div className="divide-y divide-border/60">
              <div className="grid grid-cols-[1fr_140px] items-center gap-3 px-3 py-2">
                <RowLabel hint="Total float excluding buffer (days)">Float excl.</RowLabel>
                <AutoMetric
                  value={project.totalFloatExclBuffer ?? null}
                  onSave={(v) => patch({ totalFloatExclBuffer: v })}
                  unit="d"
                  integer
                />
              </div>
              <div className="grid grid-cols-[1fr_140px] items-center gap-3 px-3 py-2">
                <RowLabel hint="Total float including buffer (days)">Float incl.</RowLabel>
                <AutoMetric
                  value={project.totalFloatInclBuffer ?? null}
                  onSave={(v) => patch({ totalFloatInclBuffer: v })}
                  unit="d"
                  integer
                />
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ── Derived ─────────────────────────────────────────────── */}
      <div className="rounded-md border border-border bg-card mt-4">
        <div className="px-4 py-2 border-b border-border text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
          Derived
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 divide-y sm:divide-y-0 sm:divide-x divide-border">
          <div className="grid grid-cols-[1fr_140px] items-center gap-3 px-3 py-2">
            <div className="min-w-0">
              <RowLabel hint="Planned minus expected completion. Positive = ahead, negative = slipping.">Schedule Buffer</RowLabel>
              <div className="text-[10px] text-muted-foreground">Planned − Expected</div>
            </div>
            <div className="h-9 flex items-center justify-end px-2.5">
              <BufferValue days={scheduleBuffer} />
            </div>
          </div>
          <div className="grid grid-cols-[1fr_140px] items-center gap-3 px-3 py-2">
            <div className="min-w-0">
              <RowLabel hint="Schedule buffer captured by the most recent monthly snapshot.">
                Buffer (M-1)
                {latestSnapshot?.periodLabel ? (
                  <span className="ml-1 text-[10px] text-muted-foreground">· {latestSnapshot.periodLabel}</span>
                ) : null}
              </RowLabel>
              <div className="text-[10px] text-muted-foreground">From latest snapshot</div>
            </div>
            <div className="h-9 flex items-center justify-end px-2.5">
              <BufferPrevValue prev={latestSnapshot?.scheduleBuffer} current={scheduleBuffer} />
            </div>
          </div>
          <div className="grid grid-cols-[1fr_140px] items-center gap-3 px-3 py-2">
            <div className="min-w-0">
              <RowLabel hint="Planned execution duration: GREEN gate planned date → WHITE gate planned date. Empty if either gate has no planned date.">Green→White</RowLabel>
              <div className="text-[10px] text-muted-foreground">SVAC denominator</div>
            </div>
            <div className="h-9 flex items-center justify-end px-2.5">
              {daysGreenToWhite == null ? (
                <span className="text-sm text-muted-foreground font-mono">—</span>
              ) : (
                <span className="text-sm font-semibold font-mono tabular-nums text-foreground">
                  {daysGreenToWhite} <span className="ml-0.5 text-[10px] text-muted-foreground font-semibold">d</span>
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Timeline */}
      <div
        className="mt-5"
        onMouseOver={onTimelineMouseOver}
        onMouseLeave={onTimelineMouseLeave}
      >
        <PhaseGateTimeline
          currentPhaseKey={project.currentPhase}
          currentGateKey={project.currentGate}
          gates={project.gates ?? []}
          lifecycleType={project.lifecycleType}
        />
      </div>
      <div className="mt-4">
        <GatesTab
          projectId={projectId}
          gates={project.gates ?? []}
          hoveredGate={hoveredGate}
          onRowHover={onGateHover}
        />
      </div>

      {/* Milestones */}
      <div className="mt-5">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-2">Milestones</div>
        <MilestonesTab projectId={projectId} milestones={project.milestones ?? []} />
      </div>
    </>
  );
}
