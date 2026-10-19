"use client";

import { useState, useMemo, useEffect, useRef, useCallback } from "react";
import { Search, X, SlidersHorizontal, ChevronDown } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { PhaseSelector } from "@/components/ui/phase-selector";
import { TierSelector } from "@/components/ui/tier-selector";
import { StatusSelector } from "@/components/ui/status-selector";
import { ListSelector, type ListOption } from "@/components/ui/list-selector";
import { PersonSelector, type PersonOption } from "@/components/ui/person-selector";
import { LocationSelector } from "@/components/ui/location-selector";
import { CategorySelector } from "@/components/ui/category-selector";
import { PROJECT_STATUSES } from "@/lib/constants";
import {
  LIFECYCLE_FILTER_OPTIONS,
  phasesValidForLifecycle,
  type LifecycleFilterValue,
} from "@/lib/lifecycle-filter";
import { cn } from "@/lib/utils";
import type { DashboardFilters, FilterOptions } from "@/types";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export type FilterFieldType =
  | "search"
  | "phase"
  | "tier"
  | "status"
  | "list"
  | "person"
  | "location"
  | "category"
  | "toggle";

export interface FilterField {
  key: keyof DashboardFilters;
  label: string;
  type: FilterFieldType;
  options?: ListOption[];
  placeholder?: string;
  colSpan?: number;
}

export interface UnifiedFilterBarProps {
  filters: DashboardFilters;
  onChange: (filters: DashboardFilters) => void;
  filterOptions?: FilterOptions;
  /** True while filterOptions are loading — shows skeleton placeholders */
  optionsLoading?: boolean;
  fields?: FilterField[];
  className?: string;
}

/* ------------------------------------------------------------------ */
/*  Preset field configs                                               */
/* ------------------------------------------------------------------ */

export const ALL_FILTER_FIELDS: FilterField[] = [
  { key: "search", label: "Search", type: "search", colSpan: 2 },
  { key: "phase", label: "Phase", type: "phase" },
  { key: "tier", label: "Tier", type: "tier" },
  { key: "status", label: "Status", type: "status", placeholder: "All Statuses" },
  { key: "division", label: "Division", type: "list", placeholder: "All Divisions" },
  { key: "factory", label: "Factory", type: "location", placeholder: "All Factories" },
  { key: "category", label: "Category", type: "category", placeholder: "All Categories" },
  { key: "pmo", label: "PMO", type: "person", placeholder: "All PMOs" },
  { key: "pm", label: "PM", type: "person", placeholder: "All PMs" },
  { key: "owner", label: "Owner", type: "person", placeholder: "All Owners" },
  { key: "sponsor", label: "Sponsor", type: "person", placeholder: "All Sponsors" },
  { key: "msrOnly", label: "MSR Only", type: "toggle" },
  { key: "excomOnly", label: "ExCom Only", type: "toggle" },
];

export const DASHBOARD_FILTER_FIELDS: FilterField[] = [
  { key: "search", label: "Search", type: "search", colSpan: 2 },
  { key: "phase", label: "Phase", type: "phase" },
  { key: "tier", label: "Tier", type: "tier" },
  { key: "factory", label: "Factory", type: "location", placeholder: "All Factories" },
];

/* ------------------------------------------------------------------ */
/*  Resolve options from FilterOptions for a given field               */
/* ------------------------------------------------------------------ */

interface ResolvedOptions {
  list: Record<string, ListOption[]>;
  person: Record<string, PersonOption[]>;
  location: { value: string; label: string; division?: string; country?: string }[];
  category: { value: string; code: string; name: string }[];
}

function resolveOptions(fo: FilterOptions | undefined): ResolvedOptions {
  if (!fo) return { list: {}, person: {}, location: [], category: [] };

  return {
    list: {
      division: fo.divisions.map((d) => ({ value: d, label: d })),
    },
    person: {
      pmo: fo.pmos,
      pm: fo.pms,
      owner: fo.owners,
      sponsor: fo.sponsors,
    },
    location: fo.factories,
    category: fo.categories,
  };
}

/* ------------------------------------------------------------------ */
/*  Debounced search input                                             */
/* ------------------------------------------------------------------ */

function SearchInput({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string | undefined) => void;
}) {
  const [local, setLocal] = useState(value);
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    setLocal(value);
  }, [value]);

  const handleChange = useCallback(
    (v: string) => {
      setLocal(v);
      clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => {
        onChange(v || undefined);
      }, 300);
    },
    [onChange],
  );

  const clear = useCallback(() => {
    setLocal("");
    clearTimeout(timerRef.current);
    onChange(undefined);
  }, [onChange]);

  useEffect(() => () => clearTimeout(timerRef.current), []);

  return (
    <div className="relative group">
      <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-etex-gray-400 pointer-events-none transition-colors group-focus-within:text-etex-orange" />
      <input
        type="text"
        placeholder="Search projects..."
        value={local}
        onChange={(e) => handleChange(e.target.value)}
        className="form-control w-full pl-8! pr-7!"
      />
      {local && (
        <button
          type="button"
          onClick={clear}
          className="absolute right-2 top-1/2 -translate-y-1/2 text-etex-gray-400 hover:text-etex-gray-600 dark:hover:text-gray-300 transition-colors"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Filter field skeleton                                              */
/* ------------------------------------------------------------------ */

function FilterSkeleton() {
  return <Skeleton className="h-8 w-full rounded" />;
}

/* ------------------------------------------------------------------ */
/*  Pill helpers                                                       */
/* ------------------------------------------------------------------ */

interface FilterPill {
  /** Field label, e.g. "Phase" — omitted for free-form (search) or boolean pills */
  field?: string;
  /** Display values (already resolved to human labels) */
  values: string[];
  onRemove: () => void;
}

function buildPills(
  filters: DashboardFilters,
  fields: FilterField[],
  resolved: ResolvedOptions,
  update: (patch: Partial<DashboardFilters>) => void,
): FilterPill[] {
  const pills: FilterPill[] = [];

  if (fields.some((field) => field.type === "phase") && filters.lifecycle) {
    const label = LIFECYCLE_FILTER_OPTIONS.find(
      (option) => option.key === filters.lifecycle,
    )?.label;
    pills.push({
      field: "Lifecycle",
      values: [label ?? filters.lifecycle],
      onRemove: () => update({ lifecycle: undefined }),
    });
  }

  for (const field of fields) {
    const k = field.key;

    if (k === "search" && filters.search) {
      pills.push({
        values: [`"${filters.search}"`],
        onRemove: () => update({ search: undefined }),
      });
      continue;
    }

    if (k === "msrOnly" && filters.msrOnly) {
      pills.push({
        values: ["MSR Only"],
        onRemove: () => update({ msrOnly: undefined }),
      });
      continue;
    }

    if (k === "excomOnly" && filters.excomOnly) {
      pills.push({
        values: ["ExCom Only"],
        onRemove: () => update({ excomOnly: undefined }),
      });
      continue;
    }

    const arr = filters[k];
    if (!Array.isArray(arr) || arr.length === 0) continue;

    let labelMap: Map<string, string>;
    if (field.type === "person") {
      const opts = resolved.person[k] ?? [];
      labelMap = new Map(opts.map((o) => [o.id, o.name]));
    } else if (field.type === "location") {
      labelMap = new Map(resolved.location.map((o) => [o.value, o.label]));
    } else if (field.type === "category") {
      labelMap = new Map(resolved.category.map((o) => [o.value, `${o.code} ${o.name}`]));
    } else if (field.type === "status") {
      labelMap = new Map(PROJECT_STATUSES.map((s) => [s.key, s.label]));
    } else {
      const opts = field.options ?? resolved.list[k] ?? [];
      labelMap = new Map(opts.map((o) => [o.value, o.label]));
    }

    pills.push({
      field: field.label,
      values: (arr as string[]).map((v) => labelMap.get(v) ?? v.replace(/_/g, " ")),
      onRemove: () => update({ [k]: undefined } as Partial<DashboardFilters>),
    });
  }

  return pills;
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function UnifiedFilterBar({
  filters,
  onChange,
  filterOptions,
  optionsLoading,
  fields = ALL_FILTER_FIELDS,
  className,
}: UnifiedFilterBarProps) {
  const [open, setOpen] = useState(false);
  const resolved = useMemo(() => resolveOptions(filterOptions), [filterOptions]);

  const update = useCallback(
    (patch: Partial<DashboardFilters>) => {
      const next = { ...filters, ...patch };
      for (const k of Object.keys(next) as (keyof DashboardFilters)[]) {
        const v = next[k];
        if (Array.isArray(v) && v.length === 0) {
          (next as Record<string, unknown>)[k] = undefined;
        }
      }
      onChange(next);
    },
    [filters, onChange],
  );

  const activeCount = fields.reduce((n, f) => {
    const v = filters[f.key];
    if (v === undefined || v === false) return n;
    if (Array.isArray(v)) return n + (v.length > 0 ? 1 : 0);
    if (typeof v === "string") return n + (v ? 1 : 0);
    if (typeof v === "boolean") return n + (v ? 1 : 0);
    return n;
  }, fields.some((field) => field.type === "phase") && filters.lifecycle ? 1 : 0);

  const pills = useMemo(
    () => buildPills(filters, fields, resolved, update),
    [filters, fields, resolved, update],
  );

  const clearAll = useCallback(() => onChange({}), [onChange]);

  /* Fields that don't need filterOptions to render */
  const staticTypes: Set<FilterFieldType> = new Set([
    "search",
    "phase",
    "tier",
    "status",
    "toggle",
  ]);

  /* Lock body scroll when mobile sheet is open */
  useEffect(() => {
    if (!open) return;
    // Only lock on mobile — desktop uses inline controls
    const mq = window.matchMedia("(min-width: 1024px)");
    if (mq.matches) return;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = ""; };
  }, [open]);

  /* Close on Escape */
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  /* ── Shared filter control renderer ── */
  const renderField = (field: FilterField) => {
    const colClass = field.colSpan === 2 ? "col-span-2 sm:col-span-1" : "";

    if (optionsLoading && !staticTypes.has(field.type)) {
      return (
        <div key={field.key} className={colClass}>
          <FilterSkeleton />
        </div>
      );
    }

    switch (field.type) {
      case "search":
        return (
          <div key={field.key} className={colClass}>
            <SearchInput
              value={filters.search ?? ""}
              onChange={(v) => update({ search: v })}
            />
          </div>
        );

      case "phase":
        return (
          <PhaseSelector
            key={field.key}
            values={filters.phase as string[] | undefined}
            onValuesChange={(v) => update({ phase: v.length ? v : undefined })}
            lifecycleFilter={filters.lifecycle ?? "GLOBAL"}
            onLifecycleFilterChange={(lifecycle: LifecycleFilterValue) =>
              update({
                lifecycle: lifecycle === "GLOBAL" ? undefined : lifecycle,
                phase: phasesValidForLifecycle(filters.phase as string[] | undefined, lifecycle),
              })
            }
            allowAll
            compact
          />
        );

      case "tier":
        return (
          <TierSelector
            key={field.key}
            values={filters.tier as string[] | undefined}
            onValuesChange={(v) => update({ tier: v.length ? v : undefined })}
            allowAll
            compact
          />
        );

      case "status":
        return (
          <StatusSelector
            key={field.key}
            values={filters.status as string[] | undefined}
            onValuesChange={(v) => update({ status: v.length ? v : undefined })}
            allowAll
            compact
            placeholder={field.placeholder ?? `All ${field.label}`}
          />
        );

      case "list": {
        const listOpts = field.options ?? resolved.list[field.key] ?? [];
        if (!field.options && listOpts.length === 0) return null;
        return (
          <ListSelector
            key={field.key}
            options={listOpts}
            values={filters[field.key] as string[] | undefined}
            onValuesChange={(v) =>
              update({ [field.key]: v.length ? v : undefined } as Partial<DashboardFilters>)
            }
            allowAll
            compact
            placeholder={field.placeholder ?? `All ${field.label}`}
          />
        );
      }

      case "location": {
        if (resolved.location.length === 0) return null;
        return (
          <LocationSelector
            key={field.key}
            options={resolved.location}
            values={filters[field.key] as string[] | undefined}
            onValuesChange={(v) =>
              update({ [field.key]: v.length ? v : undefined } as Partial<DashboardFilters>)
            }
            compact
            placeholder={field.placeholder ?? `All ${field.label}`}
          />
        );
      }

      case "category": {
        if (resolved.category.length === 0) return null;
        return (
          <CategorySelector
            key={field.key}
            options={resolved.category}
            values={filters[field.key] as string[] | undefined}
            onValuesChange={(v) =>
              update({ [field.key]: v.length ? v : undefined } as Partial<DashboardFilters>)
            }
            compact
            placeholder={field.placeholder ?? `All ${field.label}`}
          />
        );
      }

      case "person": {
        const personOpts = resolved.person[field.key] ?? [];
        if (personOpts.length === 0) return null;
        return (
          <PersonSelector
            key={field.key}
            options={personOpts}
            values={filters[field.key] as string[] | undefined}
            onValuesChange={(v) =>
              update({ [field.key]: v.length ? v : undefined } as Partial<DashboardFilters>)
            }
            allowAll
            compact
            placeholder={field.placeholder ?? `All ${field.label}`}
          />
        );
      }

      case "toggle":
        return (
          <div key={field.key} className="flex items-center gap-2 h-8">
            <Switch
              checked={(filters[field.key] as boolean) ?? false}
              onCheckedChange={(v) =>
                update({
                  [field.key]: v || undefined,
                } as Partial<DashboardFilters>)
              }
            />
            <span className="text-xs text-etex-gray-600 dark:text-gray-400 whitespace-nowrap">
              {field.label}
            </span>
          </div>
        );

      default:
        return null;
    }
  };

  /* ── Pills renderer — grouped by field with a "Field · v1, v2" chip ── */
  const pillsEl = pills.length > 0 && (
    <div className="flex flex-wrap gap-1.5 px-3 pb-2.5 border-t border-(--border) pt-2.5">
      {pills.map((pill, i) => (
        <span
          key={i}
          className="group inline-flex items-center gap-1.5 pl-2 pr-1 py-1 rounded-sm border border-etex-orange/30 bg-etex-orange/5 text-[11px] font-medium shadow-xs hover:border-etex-orange/60 hover:bg-etex-orange/10 transition-all"
        >
          {pill.field && (
            <span className="text-etex-orange font-semibold tracking-wide">
              {pill.field}
            </span>
          )}
          {pill.field && (
            <span className="h-3 w-px bg-etex-orange/30" aria-hidden />
          )}
          <span className="text-etex-gray-700 dark:text-gray-200 max-w-64 truncate">
            {pill.values.join(", ")}
          </span>
          {pill.values.length > 1 && (
            <span className="inline-flex items-center justify-center h-4 min-w-4 px-1 rounded-sm bg-etex-orange/15 text-etex-orange text-[9px] font-bold leading-none">
              {pill.values.length}
            </span>
          )}
          <button
            type="button"
            onClick={pill.onRemove}
            aria-label="Remove filter"
            className="rounded-sm p-0.5 text-etex-gray-400 hover:bg-etex-orange/20 hover:text-etex-orange transition-colors"
          >
            <X className="h-3 w-3" />
          </button>
        </span>
      ))}
    </div>
  );

  return (
    <div className={cn("card-compact", className)}>
      {/* ── Header — click anywhere to toggle. Shows an inline pill preview
              of active filters when collapsed, so users can see what's
              applied without expanding. ── */}
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 px-3 py-2 transition-colors hover:bg-(--hover)"
      >
        <SlidersHorizontal
          className={cn(
            "h-3.5 w-3.5 shrink-0 transition-colors",
            activeCount > 0 ? "text-etex-orange" : "text-etex-gray-400",
          )}
        />
        <span className="text-xs font-semibold text-(--foreground) shrink-0">
          Filters
        </span>
        {activeCount > 0 && (
          <span className="inline-flex items-center justify-center h-4 min-w-4 px-1 rounded-full bg-etex-orange text-white text-[9px] font-bold leading-none shrink-0">
            {activeCount}
          </span>
        )}

        {/* Inline pill preview when collapsed — up to 3, then "+N" */}
        {!open && pills.length > 0 && (
          <span className="hidden sm:flex items-center gap-1.5 ml-1 overflow-hidden">
            {pills.slice(0, 3).map((p, i) => (
              <span
                key={i}
                className="inline-flex items-center gap-1 max-w-44 px-1.5 py-0.5 rounded-sm border border-etex-orange/25 bg-etex-orange/5 text-[10px] font-medium"
              >
                {p.field && (
                  <>
                    <span className="text-etex-orange font-semibold shrink-0">
                      {p.field}
                    </span>
                    <span className="text-etex-orange/40 shrink-0">·</span>
                  </>
                )}
                <span className="text-etex-gray-700 dark:text-gray-200 truncate">
                  {p.values.length > 1
                    ? `${p.values[0]} +${p.values.length - 1}`
                    : p.values[0]}
                </span>
              </span>
            ))}
            {pills.length > 3 && (
              <span className="text-[10px] text-etex-gray-500 font-medium shrink-0">
                +{pills.length - 3} more
              </span>
            )}
          </span>
        )}

        <span className="flex-1" />

        {activeCount > 0 && (
          <span
            role="button"
            tabIndex={0}
            onClick={(e) => {
              e.stopPropagation();
              clearAll();
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.stopPropagation();
                clearAll();
              }
            }}
            className="text-[11px] text-etex-orange hover:text-etex-orange-dark font-medium transition-colors shrink-0"
          >
            Clear all
          </span>
        )}
        <span className="shrink-0 text-etex-gray-400 transition-transform duration-200" style={{ transform: open ? "rotate(180deg)" : "none" }}>
          <ChevronDown className="h-3.5 w-3.5" />
        </span>
      </button>

      {/* ── Desktop: inline filter controls, collapsible (lg+) ── */}
      {open && (
        <div className="hidden lg:grid lg:grid-cols-4 xl:grid-cols-6 gap-2 px-3 py-2.5 border-t border-(--border) animate-in fade-in slide-in-from-top-1 duration-150">
          {fields.map(renderField)}
        </div>
      )}

      {/* ── Mobile/tablet: bottom sheet overlay (< lg) ── */}
      {open && (
        <>
          <div
            className="lg:hidden fixed inset-0 z-40 bg-black/40 backdrop-blur-sm animate-in fade-in duration-200"
            onClick={() => setOpen(false)}
          />
          <div className="lg:hidden fixed inset-x-0 bottom-0 z-50 max-h-[85vh] flex flex-col rounded-t-2xl shadow-2xl bg-white dark:bg-[#1E2028] animate-in slide-in-from-bottom duration-300">
            {/* Sheet handle */}
            <div className="flex justify-center pt-3 pb-2">
              <div className="w-10 h-1 rounded-full bg-etex-gray-200 dark:bg-gray-700" />
            </div>

            {/* Sheet header */}
            <div className="flex items-center justify-between px-5 pb-3 border-b border-(--border)">
              <span className="text-sm font-semibold text-(--foreground)">Filters</span>
              <div className="flex items-center gap-3">
                {activeCount > 0 && (
                  <button
                    type="button"
                    onClick={clearAll}
                    className="text-xs text-etex-orange hover:text-etex-orange-dark font-medium transition-colors"
                  >
                    Clear all
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  className="rounded-full p-1.5 hover:bg-etex-gray-100 dark:hover:bg-gray-800 transition-colors"
                >
                  <X className="h-4 w-4 text-etex-gray-500" />
                </button>
              </div>
            </div>

            {/* Sheet body — scrollable */}
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {fields.map((field) => (
                <div key={field.key}>
                  <label className="text-[11px] font-semibold uppercase tracking-wide text-etex-gray-500 dark:text-gray-400 mb-1.5 block">
                    {field.label}
                  </label>
                  {renderField(field)}
                </div>
              ))}
            </div>

            {/* Sheet footer — apply button */}
            <div className="px-4 py-3 border-t border-(--border) safe-area-pb">
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="w-full py-2.5 rounded-lg bg-etex-orange text-white text-sm font-semibold hover:bg-etex-orange-dark transition-colors"
              >
                Apply Filters
                {activeCount > 0 && (
                  <span className="ml-2 inline-flex items-center justify-center h-5 min-w-5 px-1 rounded-full bg-white/20 text-[10px] font-bold">
                    {activeCount}
                  </span>
                )}
              </button>
            </div>
          </div>
        </>
      )}

      {/* ── Desktop: full pill row only when expanded (collapsed state shows
              an inline pill preview inside the header). ── */}
      {open && <div className="hidden lg:block">{pillsEl}</div>}

      {/* ── Mobile: pills always visible below header (when sheet closed) ── */}
      {!open && <div className="lg:hidden">{pillsEl}</div>}
    </div>
  );
}
