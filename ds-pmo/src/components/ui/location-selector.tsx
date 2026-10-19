"use client";

import { useState, useMemo, useRef, useEffect } from "react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { CountryFlag } from "@/components/ui/country-flag";
import { cn } from "@/lib/utils";
import { ChevronDown, Check, Search, X, MapPin, Layers } from "lucide-react";

/* ═══════════════════════════════════════════════════════════════════
   LocationSelector — factory picker grouped by division (multi-select)
   Shows factories organized under their parent division with
   group-level select/deselect, inline search, and a country flag per
   row (matches the visual treatment on the project detail page).
   ═════════════════════════════════════════════════════════════════ */

export interface LocationOption {
  value: string;
  label: string;
  division?: string;
  /** ISO-3166-1 alpha-2 country code (e.g. "AR", "FR"). */
  country?: string;
}

/* Fixed-width slot so factory names stay vertically aligned whether
   the row has a flag or not. flagcdn 4:3 ratio at width 16 = ~12px tall. */
function FlagSlot({ code }: { code?: string }) {
  return (
    <span className="inline-flex items-center justify-center w-4 h-3 shrink-0 overflow-hidden rounded-[1px]">
      {code && code.length === 2 ? (
        <CountryFlag code={code} size={16} className="object-cover" />
      ) : (
        <MapPin className="h-3 w-3 text-gray-300 dark:text-gray-600" />
      )}
    </span>
  );
}

interface LocationSelectorProps {
  options: LocationOption[];
  /** Currently selected factory names */
  values?: string[];
  onValuesChange: (v: string[]) => void;
  placeholder?: string;
  compact?: boolean;
  className?: string;
}

export function LocationSelector({
  options,
  values,
  onValuesChange,
  placeholder = "All Factories",
  compact,
  className,
}: LocationSelectorProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const selected = useMemo(() => new Set(values ?? []), [values]);
  const isAll = selected.size === 0;

  /* ── Group factories by division ── */
  const groups = useMemo(() => {
    const map = new Map<string, LocationOption[]>();
    for (const o of options) {
      const div = o.division || "Other";
      if (!map.has(div)) map.set(div, []);
      map.get(div)!.push(o);
    }
    // Sort divisions alphabetically, "Other" last
    return [...map.entries()]
      .sort(([a], [b]) => {
        if (a === "Other") return 1;
        if (b === "Other") return -1;
        return a.localeCompare(b);
      })
      .map(([division, factories]) => ({
        division,
        factories: factories.sort((a, b) => a.label.localeCompare(b.label)),
      }));
  }, [options]);

  /* ── Filtered groups (search) ── */
  const filteredGroups = useMemo(() => {
    if (!query) return groups;
    const q = query.toLowerCase();
    return groups
      .map((g) => ({
        ...g,
        factories: g.factories.filter(
          (f) =>
            f.label.toLowerCase().includes(q) ||
            g.division.toLowerCase().includes(q) ||
            (f.country ?? "").toLowerCase().includes(q),
        ),
      }))
      .filter((g) => g.factories.length > 0);
  }, [groups, query]);

  const showSearch = options.length > 6;

  useEffect(() => {
    if (open && showSearch) setTimeout(() => inputRef.current?.focus(), 0);
    if (!open) setQuery("");
  }, [open, showSearch]);

  /* ── Handlers ── */
  const toggle = (value: string) => {
    const next = new Set(selected);
    if (next.has(value)) next.delete(value);
    else next.add(value);
    onValuesChange([...next]);
  };

  const selectAll = () => {
    onValuesChange([]);
    setOpen(false);
  };

  const toggleDivision = (division: string) => {
    const group = groups.find((g) => g.division === division);
    if (!group) return;
    const keys = group.factories.map((f) => f.value);
    const allSelected = keys.every((k) => selected.has(k));
    if (allSelected) {
      const next = new Set(selected);
      keys.forEach((k) => next.delete(k));
      onValuesChange([...next]);
    } else {
      onValuesChange([...new Set([...selected, ...keys])]);
    }
  };

  /* ── Trigger label + flag ── */
  const triggerSingle = useMemo(() => {
    if (!isAll && selected.size === 1) {
      return options.find((o) => o.value === [...selected][0]) ?? null;
    }
    return null;
  }, [isAll, selected, options]);

  const triggerLabel = useMemo(() => {
    if (isAll) return null;
    if (triggerSingle) return triggerSingle.label;
    return `${selected.size} factories`;
  }, [isAll, selected, triggerSingle]);

  return (
    <Popover open={open} onOpenChange={setOpen}>
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
          {triggerLabel ? (
            <>
              {triggerSingle ? (
                <FlagSlot code={triggerSingle.country} />
              ) : (
                <MapPin className="h-3 w-3 text-gray-400 shrink-0" />
              )}
              <span className="truncate font-medium text-gray-900 dark:text-gray-100">
                {triggerLabel}
              </span>
            </>
          ) : (
            <span className="text-gray-400 dark:text-gray-500 truncate">
              {placeholder}
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

      <PopoverContent
        align="start"
        className="w-(--radix-popover-trigger-width) min-w-60 p-0 overflow-hidden shadow-xl border border-gray-200/80 dark:border-(--border) rounded-lg dark:shadow-[0_8px_24px_rgba(0,0,0,0.4)]"
      >
        {/* Search */}
        {showSearch && (
          <div className="relative border-b border-gray-100 dark:border-(--border)">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3 w-3 text-gray-400 pointer-events-none" />
            <input
              ref={inputRef}
              type="text"
              placeholder="Search factories, divisions, country..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="w-full bg-transparent text-xs py-2 pl-7 pr-7 outline-none placeholder:text-gray-400 text-gray-900 dark:text-gray-100"
            />
            {query && (
              <button
                type="button"
                onClick={() => setQuery("")}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 transition-colors"
              >
                <X className="h-3 w-3" />
              </button>
            )}
          </div>
        )}

        <div className="max-h-72 overflow-y-auto">
          {/* All option */}
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
              <span className="text-xs font-medium text-gray-600 dark:text-gray-300">{placeholder}</span>
              {isAll && <Check className="ml-auto h-3.5 w-3.5 text-gray-400 shrink-0" />}
            </button>
          </div>

          {/* Grouped factories */}
          {filteredGroups.map(({ division, factories }, gi) => {
            const divKeys = factories.map((f) => f.value);
            const allDivSelected = divKeys.every((k) => selected.has(k));

            return (
              <div key={division}>
                {/* Division header */}
                <button
                  type="button"
                  onClick={() => toggleDivision(division)}
                  className={cn(
                    "sticky top-0 z-10 w-full flex items-center gap-2 px-3 py-1.5 bg-white/95 dark:bg-(--card)/95 backdrop-blur-sm text-left transition-colors hover:bg-gray-50 dark:hover:bg-(--muted)",
                    gi > 0 || true ? "border-t border-gray-100 dark:border-(--border)" : "",
                  )}
                >
                  <Layers className="h-3 w-3 text-gray-400 shrink-0" />
                  <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-gray-400 dark:text-gray-500">
                    {division}
                  </span>
                  <span className="flex-1 h-px bg-gray-100 dark:bg-(--border)" />
                  {allDivSelected && (
                    <Check className="h-3 w-3 text-etex-orange shrink-0" />
                  )}
                </button>

                {/* Factory rows */}
                <div className="px-1.5 pb-0.5">
                  {factories.map((f, i) => {
                    const sel = selected.has(f.value);
                    return (
                      <button
                        // Factory names aren't unique in the DB (e.g. multiple
                        // "Etex Services (BE)" rows), so the React key includes
                        // index. The `value` (name) is what the filter URL uses.
                        key={`${f.value}|${i}`}
                        type="button"
                        onClick={() => toggle(f.value)}
                        className={cn(
                          "w-full flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left transition-all duration-150 group",
                          sel
                            ? "bg-gray-50 dark:bg-(--muted)"
                            : "hover:bg-gray-50/70 dark:hover:bg-(--muted)",
                        )}
                        style={sel ? { borderLeft: "2px solid var(--etex-orange)", paddingLeft: 8 } : undefined}
                      >
                        <FlagSlot code={f.country} />
                        <span
                          className={cn(
                            "text-xs font-medium leading-tight flex-1 truncate",
                            sel ? "text-gray-900 dark:text-gray-100" : "text-gray-600 dark:text-gray-300",
                          )}
                        >
                          {f.label}
                        </span>
                        {sel && <Check className="h-3.5 w-3.5 shrink-0 text-etex-orange" />}
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })}

          {filteredGroups.length === 0 && (
            <div className="px-2.5 py-3 text-xs text-gray-400 text-center">No results</div>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
