"use client";

import { useState, useMemo } from "react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { getPhasesForLifecycle, type Phase } from "@/lib/constants";
import {
  getPhasesForLifecycleFilter,
  LIFECYCLE_FILTER_OPTIONS,
  type LifecycleFilterValue,
} from "@/lib/lifecycle-filter";
import { cn } from "@/lib/utils";
import { ChevronDown, Check, Layers } from "lucide-react";
import { useReadOnly } from "@/components/ui/read-only-context";

/* ═══════════════════════════════════════════════════════════════════
   PhaseSelector — enterprise PMO phase picker
   Supports single-select (default) and multi-select for filters.
   ═════════════════════════════════════════════════════════════════ */

interface PhaseSelectorProps {
  /** Single value (backward-compat) */
  value?: string;
  /** Multi values — takes precedence over `value` when provided */
  values?: string[];
  /** Single-select callback */
  onValueChange?: (key: string) => void;
  /** Multi-select callback */
  onValuesChange?: (keys: string[]) => void;
  /** Show "All Phases" reset option */
  allowAll?: boolean;
  /** Compact 32px height */
  compact?: boolean;
  /** Lifecycle type — determines phase labels */
  lifecycleType?: string | null;
  /** Portfolio lifecycle filter — Global means both persisted lifecycles. */
  lifecycleFilter?: LifecycleFilterValue;
  onLifecycleFilterChange?: (value: LifecycleFilterValue) => void;
  className?: string;
}

const STAGE_ORDER = [
  "Pre-Project",
  "Project Planning",
  "Project Execution",
  "Post Project",
  "Closed",
] as const;

const STAGE_SHORT: Record<string, string> = {
  "Pre-Project": "Pre-Project",
  "Project Planning": "Planning",
  "Project Execution": "Execution",
  "Post Project": "Post",
  "Closed": "Closed",
};

function isLightPhase(phase: Phase) {
  return phase.key === "BENEFITS";
}

function groupedPhases(phases: Phase[]) {
  return STAGE_ORDER.map((group) => ({
    group,
    phases: phases.filter((p) => p.stageGroup === group),
  })).filter((g) => g.phases.length > 0);
}

/** Tiny color dot for a phase */
function PhaseDot({ phase, size = 8 }: { phase: Phase; size?: number }) {
  return (
    <span
      className="inline-block rounded-full shrink-0"
      style={{
        width: size,
        height: size,
        backgroundColor: isLightPhase(phase) ? "#9CA3AF" : phase.color,
        border: isLightPhase(phase) ? "1px solid #D1D5DB" : undefined,
      }}
    />
  );
}

export function PhaseSelector({
  value,
  values,
  onValueChange,
  onValuesChange,
  allowAll,
  compact,
  lifecycleType,
  lifecycleFilter,
  onLifecycleFilterChange,
  className,
}: PhaseSelectorProps) {
  const readOnly = useReadOnly();
  const [open, setOpen] = useState(false);
  const multi = !!onValuesChange;

  // In multi-select mode lifecycle is controlled by the portfolio filter.
  // In single-select mode a project's persisted lifecycle determines phases.
  const showLifecycleToggle = multi;
  const selectedLifecycle = lifecycleFilter ?? "GLOBAL";

  const phases = useMemo(
    () => multi
      ? getPhasesForLifecycleFilter(selectedLifecycle)
      : getPhasesForLifecycle(lifecycleType),
    [multi, selectedLifecycle, lifecycleType],
  );
  // Resolve labels/colors against BOTH lifecycles for the trigger — a
  // selected key might live in the lifecycle the user isn't currently
  // viewing, but we still need to render it.
  const allPhasesIndex = useMemo(() => {
    const map = new Map<string, Phase>();
    for (const phase of getPhasesForLifecycleFilter("GLOBAL")) {
      map.set(phase.key, phase);
    }
    return map;
  }, []);
  const selected = useMemo(() => {
    if (multi) return new Set(values ?? []);
    return new Set(value && value !== "__all__" ? [value] : []);
  }, [multi, value, values]);

  const groups = useMemo(() => groupedPhases(phases), [phases]);
  const isAll = selected.size === 0;

  const current = useMemo(() => {
    if (selected.size === 1) {
      // Look across all lifecycles so the trigger still labels the chip
      // even when the user has flipped the popover to the other lifecycle.
      return allPhasesIndex.get([...selected][0]);
    }
    return undefined;
  }, [selected, allPhasesIndex]);

  /* ── Handlers ── */
  const togglePhase = (key: string) => {
    if (multi) {
      const next = new Set(selected);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      onValuesChange!([...next]);
    } else {
      onValueChange?.(key);
      setOpen(false);
    }
  };

  const selectAll = () => {
    if (multi) onValuesChange!([]);
    else onValueChange?.("__all__");
    setOpen(false);
  };

  const selectGroup = (group: string) => {
    const keys = phases.filter((p) => p.stageGroup === group).map((p) => p.key);
    if (multi) {
      const allSelected = keys.every((k) => selected.has(k));
      if (allSelected) {
        const next = new Set(selected);
        keys.forEach((k) => next.delete(k));
        onValuesChange!([...next]);
      } else {
        onValuesChange!([...new Set([...selected, ...keys])]);
      }
    } else {
      // Single-select: select first phase of the group
      onValueChange?.(keys[0]);
      setOpen(false);
    }
  };

  /* ── Trigger label ── */
  const triggerLabel = useMemo(() => {
    if (isAll) return null;
    if (current) return current.shortLabel;
    if (selected.size > 1) return `${selected.size} phases`;
    return null;
  }, [isAll, current, selected]);

  /* ── Read-only ── */
  if (readOnly) {
    return (
      <div
        className={cn(
          "form-control-readonly w-full flex items-center gap-2",
          compact ? "h-8 text-xs" : "h-9 text-sm",
          className,
        )}
      >
        {current ? (
          <>
            <PhaseDot phase={current} size={compact ? 8 : 10} />
            <span className="truncate font-medium text-gray-900 dark:text-gray-100">
              {current.shortLabel}
            </span>
          </>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </div>
    );
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      {/* ── Trigger ── */}
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn(
            "form-control w-full flex items-center gap-2 text-left transition-all",
            compact ? "h-8 text-xs" : "h-9 text-sm",
            !isAll && "ring-1 ring-etex-orange/20 border-etex-orange/30",
            className,
          )}
        >
          {current ? (
            <>
              <PhaseDot phase={current} size={compact ? 8 : 10} />
              <span className="truncate font-medium text-gray-900 dark:text-gray-100">
                {triggerLabel}
              </span>
            </>
          ) : selected.size > 1 ? (
            <>
              <div className="flex items-center -space-x-0.5">
                {[...selected].slice(0, 5).map((k) => {
                  const p = allPhasesIndex.get(k);
                  return p ? <PhaseDot key={k} phase={p} size={7} /> : null;
                })}
              </div>
              <span className="truncate font-medium text-gray-900 dark:text-gray-100">
                {triggerLabel}
              </span>
            </>
          ) : (
            <span className="text-gray-400 dark:text-gray-500 truncate">
              {allowAll ? "All Phases" : "Select phase…"}
            </span>
          )}
          <ChevronDown
            className={cn(
              "ml-auto shrink-0 text-gray-400 dark:text-gray-500 transition-transform duration-200",
              compact ? "h-3 w-3" : "h-3.5 w-3.5",
              open && "rotate-180",
            )}
          />
        </button>
      </PopoverTrigger>

      {/* ── Dropdown ── */}
      <PopoverContent
        align="start"
        className="w-65 p-0 overflow-hidden shadow-xl border border-gray-200/80 dark:border-(--border) rounded-lg dark:shadow-[0_8px_24px_rgba(0,0,0,0.4)]"
      >
        {/* Lifecycle toggle — Global is the union of EE and IT projects/phases. */}
        {showLifecycleToggle && (
          <div
            role="tablist"
            aria-label="Lifecycle"
            className="flex gap-1 p-1 border-b border-gray-100 dark:border-(--border) bg-gray-50/60 dark:bg-(--muted)/40"
          >
            {LIFECYCLE_FILTER_OPTIONS.map((lc) => {
              const active = lc.key === selectedLifecycle;
              return (
                <button
                  key={lc.key}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  onClick={() => onLifecycleFilterChange?.(lc.key)}
                  className={cn(
                    "flex-1 rounded-md px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.06em] transition-all duration-150",
                    active
                      ? "bg-white dark:bg-(--card) text-gray-900 dark:text-gray-100 shadow-xs ring-1 ring-gray-200 dark:ring-(--border)"
                      : "text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200",
                  )}
                >
                  {lc.label}
                </button>
              );
            })}
          </div>
        )}

        {/* Progress bar */}
        <div className="flex rounded-t-lg overflow-hidden" style={{ height: 4 }}>
          {phases.map((p) => (
            <div
              key={p.key}
              className="flex-1 transition-all duration-200"
              style={{
                backgroundColor: isLightPhase(p) ? "#D1D5DB" : p.color,
                opacity: selected.has(p.key) || isAll ? 1 : 0.2,
              }}
            />
          ))}
        </div>

        <div className="max-h-90 overflow-y-auto">
          {/* All Phases option */}
          {allowAll && (
            <div className="px-1.5 pt-1.5">
              <button
                type="button"
                onClick={selectAll}
                className={cn(
                  "w-full flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left transition-all duration-150",
                  isAll
                    ? "bg-gray-50 ring-1 ring-gray-200 dark:bg-(--muted) dark:ring-(--border)"
                    : "hover:bg-gray-50/70 dark:hover:bg-(--muted)",
                )}
              >
                <span className="inline-flex items-center justify-center w-2 h-2 rounded-full shrink-0 border border-dashed border-gray-400 dark:border-gray-500" />
                <span className="text-xs font-medium text-gray-600 dark:text-gray-300">All Phases</span>
                {isAll && <Check className="ml-auto h-3.5 w-3.5 text-gray-400 shrink-0" />}
              </button>
            </div>
          )}

          {/* Grouped phases */}
          {groups.map(({ group, phases }, gi) => {
            const groupKeys = phases.map((p) => p.key);
            const allGroupSelected = groupKeys.every((k) => selected.has(k));

            return (
              <div key={group}>
                {/* Group header — clickable for group shortcuts */}
                <button
                  type="button"
                  onClick={() => selectGroup(group)}
                  className={cn(
                    "sticky top-0 z-10 w-full flex items-center gap-2 px-3 py-1.5 bg-white/95 dark:bg-(--card)/95 backdrop-blur-sm text-left transition-colors hover:bg-gray-50 dark:hover:bg-(--muted)",
                    gi > 0 || allowAll ? "border-t border-gray-100 dark:border-(--border)" : "",
                  )}
                >
                  <Layers className="h-3 w-3 text-gray-400 shrink-0" />
                  <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-gray-400 dark:text-gray-500">
                    {STAGE_SHORT[group] ?? group}
                  </span>
                  <span className="flex-1 h-px bg-gray-100 dark:bg-(--border)" />
                  {multi && allGroupSelected && (
                    <Check className="h-3 w-3 text-etex-orange shrink-0" />
                  )}
                </button>

                {/* Phase rows — compact, no descriptions */}
                <div className="px-1.5 pb-0.5">
                  {phases.map((p) => {
                    const sel = selected.has(p.key);

                    return (
                      <button
                        key={p.key}
                        type="button"
                        onClick={() => togglePhase(p.key)}
                        className={cn(
                          "w-full flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left transition-all duration-150 group",
                          sel
                            ? "bg-gray-50 dark:bg-(--muted)"
                            : "hover:bg-gray-50/70 dark:hover:bg-(--muted)",
                        )}
                        style={
                          sel
                            ? { borderLeft: `2px solid ${isLightPhase(p) ? "#6B7280" : p.color}`, paddingLeft: 8 }
                            : undefined
                        }
                      >
                        <PhaseDot phase={p} size={8} />
                        <span
                          className={cn(
                            "text-xs font-medium leading-tight flex-1",
                            sel ? "text-gray-900 dark:text-gray-100" : "text-gray-600 dark:text-gray-300",
                          )}
                        >
                          {p.shortLabel}
                        </span>
                        {sel && (
                          <Check
                            className="h-3.5 w-3.5 shrink-0"
                            style={{ color: isLightPhase(p) ? "#6B7280" : p.color }}
                          />
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </PopoverContent>
    </Popover>
  );
}
