"use client";

import { useState, useMemo, useRef, useEffect } from "react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn, getInitials } from "@/lib/utils";
import { ChevronDown, Check, Search, X, User } from "lucide-react";

/* ═══════════════════════════════════════════════════════════════════
   PersonSelector — searchable single/multi-select for people
   Used for: PM, PMO, Owner, Sponsor filters
   ═════════════════════════════════════════════════════════════════ */

export interface PersonOption {
  id: string;
  name: string;
}

interface PersonSelectorProps {
  /** Available people */
  options: PersonOption[];
  /** Placeholder shown when nothing is selected */
  placeholder?: string;
  /** Single value */
  value?: string;
  /** Multi values — takes precedence */
  values?: string[];
  onValueChange?: (v: string) => void;
  onValuesChange?: (v: string[]) => void;
  allowAll?: boolean;
  compact?: boolean;
  className?: string;
}

function Initials({ name, size = 20 }: { name: string; size?: number }) {
  return (
    <span
      className="inline-flex items-center justify-center rounded-full bg-etex-orange/15 text-etex-orange shrink-0 font-mono font-bold"
      style={{ width: size, height: size, fontSize: size * 0.4 }}
    >
      {getInitials(name)}
    </span>
  );
}

export function PersonSelector({
  options,
  placeholder = "All",
  value,
  values,
  onValueChange,
  onValuesChange,
  allowAll,
  compact,
  className,
}: PersonSelectorProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const multi = !!onValuesChange;

  const selected = useMemo(() => {
    if (multi) return new Set(values ?? []);
    return new Set(value && value !== "__all__" ? [value] : []);
  }, [multi, value, values]);

  const isAll = selected.size === 0;

  const filtered = useMemo(() => {
    if (!query) return options;
    const q = query.toLowerCase();
    return options.filter((o) => o.name.toLowerCase().includes(q));
  }, [options, query]);

  useEffect(() => {
    if (open && options.length > 4) {
      setTimeout(() => inputRef.current?.focus(), 0);
    }
    if (!open) setQuery("");
  }, [open, options.length]);

  const toggle = (id: string) => {
    if (multi) {
      const next = new Set(selected);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      onValuesChange!([...next]);
    } else {
      onValueChange?.(id);
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
      const p = options.find((o) => o.id === [...selected][0]);
      return p?.name ?? null;
    }
    return `${selected.size} people`;
  }, [isAll, selected, options]);

  if (options.length === 0) return null;

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
              <User className="h-3 w-3 text-gray-400 shrink-0" />
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
        className="w-56 p-0 overflow-hidden shadow-xl border border-gray-200/80 dark:border-(--border) rounded-lg dark:shadow-[0_8px_24px_rgba(0,0,0,0.4)]"
      >
        {/* Search */}
        {options.length > 4 && (
          <div className="relative border-b border-gray-100 dark:border-(--border)">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3 w-3 text-gray-400 pointer-events-none" />
            <input
              ref={inputRef}
              type="text"
              placeholder="Search people..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="w-full bg-transparent text-xs py-2 pl-7 pr-7 outline-none placeholder:text-gray-400 text-gray-900 dark:text-gray-100"
            />
            {query && (
              <button
                type="button"
                onClick={() => setQuery("")}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
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

          {filtered.map((p) => {
            const sel = selected.has(p.id);
            return (
              <button
                key={p.id}
                type="button"
                onClick={() => toggle(p.id)}
                className={cn(
                  "w-full flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left transition-all duration-150",
                  sel
                    ? "bg-gray-50 dark:bg-(--muted)"
                    : "hover:bg-gray-50/70 dark:hover:bg-(--muted)",
                )}
                style={sel ? { borderLeft: "2px solid var(--etex-orange)", paddingLeft: 8 } : undefined}
              >
                <Initials name={p.name} size={18} />
                <span
                  className={cn(
                    "text-xs font-medium flex-1 truncate",
                    sel ? "text-gray-900 dark:text-gray-100" : "text-gray-600 dark:text-gray-300",
                  )}
                >
                  {p.name}
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
