"use client";

import { useState, useMemo, useRef, useEffect } from "react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import { ChevronDown, Check, Search, X } from "lucide-react";

/* ═══════════════════════════════════════════════════════════════════
   ListSelector — generic searchable single/multi-select popover
   Used for: Factory, Division, Category, and any string-list filter.
   ═════════════════════════════════════════════════════════════════ */

export interface ListOption {
  value: string;
  label: string;
  /** Optional search text (if different from label, e.g. includes code + name) */
  searchText?: string;
  /**
   * Arbitrary data passed through to renderOption. Typed as `any` so callers
   * can attach a domain-specific shape without making the selector generic.
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data?: any;
}

interface ListSelectorProps {
  options: ListOption[];
  placeholder?: string;
  value?: string;
  values?: string[];
  onValueChange?: (v: string) => void;
  onValuesChange?: (v: string[]) => void;
  allowAll?: boolean;
  searchThreshold?: number;
  compact?: boolean;
  accentColor?: string;
  className?: string;
  /** Custom renderer for each option row */
  renderOption?: (option: ListOption, selected: boolean) => React.ReactNode;
  /** Custom renderer for the trigger label (when a single value is selected) */
  renderSelected?: (option: ListOption) => React.ReactNode;
}

export function ListSelector({
  options,
  placeholder = "Select…",
  value,
  values,
  onValueChange,
  onValuesChange,
  allowAll,
  searchThreshold = 6,
  compact,
  accentColor = "#E8713A",
  className,
  renderOption,
  renderSelected,
}: ListSelectorProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const multi = !!onValuesChange;
  const showSearch = options.length > searchThreshold;

  const selected = useMemo(() => {
    if (multi) return new Set(values ?? []);
    return new Set(value && value !== "__all__" ? [value] : []);
  }, [multi, value, values]);

  const isAll = selected.size === 0;

  const filtered = useMemo(() => {
    if (!query) return options;
    const q = query.toLowerCase();
    return options.filter((o) => (o.searchText ?? o.label).toLowerCase().includes(q));
  }, [options, query]);

  useEffect(() => {
    if (open && showSearch) {
      setTimeout(() => inputRef.current?.focus(), 0);
    }
    if (!open) setQuery("");
  }, [open, showSearch]);

  const toggle = (key: string) => {
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

  const triggerLabel = useMemo(() => {
    if (isAll) return null;
    if (selected.size === 1) {
      const o = options.find((o) => o.value === [...selected][0]);
      if (!o) return null;
      if (renderSelected) return renderSelected(o);
      return o.label;
    }
    return `${selected.size} selected`;
  }, [isAll, selected, options, renderSelected]);

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
            <span className="truncate font-medium text-gray-900 dark:text-gray-100 inline-flex items-center gap-1.5">
              {triggerLabel}
            </span>
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
        className="w-(--radix-popover-trigger-width) min-w-56 p-0 overflow-hidden shadow-xl border border-gray-200/80 dark:border-(--border) rounded-lg dark:shadow-[0_8px_24px_rgba(0,0,0,0.4)]"
      >
        {showSearch && (
          <div className="relative border-b border-gray-100 dark:border-(--border)">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3 w-3 text-gray-400 pointer-events-none" />
            <input
              ref={inputRef}
              type="text"
              placeholder="Search..."
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

        <div className="max-h-60 overflow-y-auto p-1.5">
          {allowAll && (
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
              <span className="w-2 h-2 rounded-full shrink-0 border border-dashed border-gray-400 dark:border-gray-500" />
              <span className="text-xs font-medium text-gray-600 dark:text-gray-300">{placeholder}</span>
              {isAll && <Check className="ml-auto h-3.5 w-3.5 text-gray-400 shrink-0" />}
            </button>
          )}

          {filtered.length === 0 && (
            <div className="px-2.5 py-3 text-xs text-gray-400 text-center">No results</div>
          )}
          {filtered.map((o) => {
            const sel = selected.has(o.value);
            return (
              <button
                key={o.value}
                type="button"
                onClick={() => toggle(o.value)}
                className={cn(
                  "w-full flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left transition-all duration-150",
                  sel
                    ? "bg-gray-50 dark:bg-(--muted)"
                    : "hover:bg-gray-50/70 dark:hover:bg-(--muted)",
                )}
                style={sel ? { borderLeft: `2px solid ${accentColor}`, paddingLeft: 8 } : undefined}
              >
                {renderOption ? (
                  <span className="flex-1 min-w-0">{renderOption(o, sel)}</span>
                ) : (
                  <span
                    className={cn(
                      "text-xs font-medium flex-1 truncate",
                      sel ? "text-gray-900 dark:text-gray-100" : "text-gray-600 dark:text-gray-300",
                    )}
                  >
                    {o.label}
                  </span>
                )}
                {sel && <Check className="h-3.5 w-3.5 shrink-0" style={{ color: accentColor }} />}
              </button>
            );
          })}
        </div>
      </PopoverContent>
    </Popover>
  );
}
