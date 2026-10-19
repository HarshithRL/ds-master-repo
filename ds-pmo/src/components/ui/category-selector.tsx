"use client";

import { useState, useMemo, useRef, useEffect } from "react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import { ChevronDown, Check, Search, X, Tag } from "lucide-react";

/* ═══════════════════════════════════════════════════════════════════
   CategorySelector — category picker with code + name display
   Shows bold category code followed by the descriptive name.
   Supports single-select and multi-select for filters.
   ═════════════════════════════════════════════════════════════════ */

export interface CategoryOption {
  value: string; // category name (used as filter value)
  code: string;  // short code e.g. "CAP"
  name: string;  // full name e.g. "Capacity"
}

interface CategorySelectorProps {
  options: CategoryOption[];
  /** Multi-select values (category names) */
  values?: string[];
  onValuesChange: (v: string[]) => void;
  placeholder?: string;
  compact?: boolean;
  className?: string;
}

export function CategorySelector({
  options,
  values,
  onValuesChange,
  placeholder = "All Categories",
  compact,
  className,
}: CategorySelectorProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const selected = useMemo(() => new Set(values ?? []), [values]);
  const isAll = selected.size === 0;
  const showSearch = options.length > 6;

  const filtered = useMemo(() => {
    if (!query) return options;
    const q = query.toLowerCase();
    return options.filter(
      (o) =>
        o.code.toLowerCase().includes(q) ||
        o.name.toLowerCase().includes(q),
    );
  }, [options, query]);

  useEffect(() => {
    if (open && showSearch) setTimeout(() => inputRef.current?.focus(), 0);
    if (!open) setQuery("");
  }, [open, showSearch]);

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

  /* ── Trigger label ── */
  const triggerLabel = useMemo(() => {
    if (isAll) return null;
    if (selected.size === 1) {
      const o = options.find((o) => o.value === [...selected][0]);
      if (!o) return null;
      return { code: o.code, name: o.name };
    }
    return { count: selected.size };
  }, [isAll, selected, options]);

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
              <Tag className="h-3 w-3 text-gray-400 shrink-0" />
              {"code" in triggerLabel ? (
                <>
                  <span className="font-bold">{triggerLabel.code}</span>
                  <span className="truncate">{triggerLabel.name}</span>
                </>
              ) : (
                <span>{triggerLabel.count} categories</span>
              )}
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
        {/* Search */}
        {showSearch && (
          <div className="relative border-b border-gray-100 dark:border-(--border)">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3 w-3 text-gray-400 pointer-events-none" />
            <input
              ref={inputRef}
              type="text"
              placeholder="Search categories..."
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
          {/* All option */}
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
                style={sel ? { borderLeft: "2px solid var(--etex-orange)", paddingLeft: 8 } : undefined}
              >
                <span
                  className={cn(
                    "inline-flex items-center gap-1.5 text-xs font-medium flex-1 truncate",
                    sel ? "text-gray-900 dark:text-gray-100" : "text-gray-600 dark:text-gray-300",
                  )}
                >
                  <span className="font-bold shrink-0">{o.code}</span>
                  <span className="truncate">{o.name}</span>
                </span>
                {sel && <Check className="h-3.5 w-3.5 shrink-0 text-etex-orange" />}
              </button>
            );
          })}
        </div>
      </PopoverContent>
    </Popover>
  );
}
