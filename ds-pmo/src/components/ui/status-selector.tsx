"use client";

import { useState, useMemo } from "react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { PROJECT_STATUSES } from "@/lib/constants";
import { cn } from "@/lib/utils";
import { ChevronDown, Check } from "lucide-react";

/* ═══════════════════════════════════════════════════════════════════
   StatusSelector — single or multi-select project status picker
   ═════════════════════════════════════════════════════════════════ */

interface StatusSelectorProps {
  /** Single value */
  value?: string;
  /** Multi values — takes precedence */
  values?: string[];
  onValueChange?: (key: string) => void;
  onValuesChange?: (keys: string[]) => void;
  allowAll?: boolean;
  compact?: boolean;
  className?: string;
  placeholder?: string;
}

export function StatusSelector({
  value,
  values,
  onValueChange,
  onValuesChange,
  allowAll,
  compact,
  className,
  placeholder,
}: StatusSelectorProps) {
  const [open, setOpen] = useState(false);
  const multi = !!onValuesChange;

  const selected = useMemo(() => {
    if (multi) return new Set(values ?? []);
    return new Set(value && value !== "__all__" ? [value] : []);
  }, [multi, value, values]);

  const isAll = selected.size === 0;

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

  const current =
    selected.size === 1 ? PROJECT_STATUSES.find((s) => s.key === [...selected][0]) : undefined;

  const triggerLabel = useMemo(() => {
    if (isAll) return null;
    if (current) return current.label;
    return `${selected.size} statuses`;
  }, [isAll, current, selected]);

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
          {current ? (
            <>
              <span
                className="inline-block w-2 h-2 rounded-full shrink-0"
                style={{ backgroundColor: current.color }}
              />
              <span className="truncate font-medium text-gray-900 dark:text-gray-100">
                {triggerLabel}
              </span>
            </>
          ) : selected.size > 1 ? (
            <>
              <div className="flex items-center -space-x-0.5">
                {[...selected].map((k) => {
                  const s = PROJECT_STATUSES.find((s) => s.key === k);
                  return s ? (
                    <span
                      key={k}
                      className="inline-block w-2 h-2 rounded-full"
                      style={{ backgroundColor: s.color }}
                    />
                  ) : null;
                })}
              </div>
              <span className="truncate font-medium text-gray-900 dark:text-gray-100">
                {triggerLabel}
              </span>
            </>
          ) : (
            <span className="text-gray-400 dark:text-gray-500 truncate">
              {placeholder ?? (allowAll ? "All Statuses" : "Select status…")}
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
        className="w-56 p-1.5 shadow-xl border border-gray-200/80 dark:border-(--border) rounded-lg dark:shadow-[0_8px_24px_rgba(0,0,0,0.4)]"
      >
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
            <span className="text-xs font-medium text-gray-600 dark:text-gray-300">
              All Statuses
            </span>
            {isAll && <Check className="ml-auto h-3.5 w-3.5 text-gray-400 shrink-0" />}
          </button>
        )}

        {PROJECT_STATUSES.map((s) => {
          const sel = selected.has(s.key);
          return (
            <button
              key={s.key}
              type="button"
              onClick={() => toggle(s.key)}
              className={cn(
                "w-full flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left transition-all duration-150",
                sel
                  ? "bg-gray-50 dark:bg-(--muted)"
                  : "hover:bg-gray-50/70 dark:hover:bg-(--muted)",
              )}
              style={sel ? { borderLeft: `2px solid ${s.color}`, paddingLeft: 8 } : undefined}
            >
              <span
                className="inline-block w-2 h-2 rounded-full shrink-0"
                style={{ backgroundColor: s.color }}
              />
              <span
                className={cn(
                  "text-xs font-medium flex-1",
                  sel
                    ? "text-gray-900 dark:text-gray-100"
                    : "text-gray-600 dark:text-gray-300",
                )}
              >
                {s.label}
              </span>
              {sel && (
                <Check className="h-3.5 w-3.5 shrink-0" style={{ color: s.color }} />
              )}
            </button>
          );
        })}
      </PopoverContent>
    </Popover>
  );
}
