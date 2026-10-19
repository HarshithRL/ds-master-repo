"use client";

import { useState, useMemo } from "react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import { ChevronDown, Check } from "lucide-react";

/* ═══════════════════════════════════════════════════════════════════
   TierSelector — single or multi-select tier picker
   ═════════════════════════════════════════════════════════════════ */

interface TierSelectorProps {
  /** Single value */
  value?: string;
  /** Multi values — takes precedence */
  values?: string[];
  onValueChange?: (key: string) => void;
  onValuesChange?: (keys: string[]) => void;
  allowAll?: boolean;
  compact?: boolean;
  className?: string;
}

const TIER_LIST = [
  { key: "TIER_1", label: "Tier 1", desc: "Strategic", color: "#DC2626" },
  { key: "TIER_2", label: "Tier 2", desc: "Medium", color: "#F97316" },
  { key: "TIER_3", label: "Tier 3", desc: "Operational", color: "#3B82F6" },
];

export function TierSelector({
  value,
  values,
  onValueChange,
  onValuesChange,
  allowAll,
  compact,
  className,
}: TierSelectorProps) {
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

  const triggerLabel = useMemo(() => {
    if (isAll) return null;
    if (selected.size === 1) {
      const t = TIER_LIST.find((t) => t.key === [...selected][0]);
      return t ? `${t.label}` : null;
    }
    return `${selected.size} tiers`;
  }, [isAll, selected]);

  const current = selected.size === 1 ? TIER_LIST.find((t) => t.key === [...selected][0]) : undefined;

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
                  const t = TIER_LIST.find((t) => t.key === k);
                  return t ? (
                    <span key={k} className="inline-block w-2 h-2 rounded-full" style={{ backgroundColor: t.color }} />
                  ) : null;
                })}
              </div>
              <span className="truncate font-medium text-gray-900 dark:text-gray-100">
                {triggerLabel}
              </span>
            </>
          ) : (
            <span className="text-gray-400 dark:text-gray-500 truncate">
              {allowAll ? "All Tiers" : "Select tier…"}
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
        className="w-52 p-1.5 shadow-xl border border-gray-200/80 dark:border-(--border) rounded-lg dark:shadow-[0_8px_24px_rgba(0,0,0,0.4)]"
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
            <span className="text-xs font-medium text-gray-600 dark:text-gray-300">All Tiers</span>
            {isAll && <Check className="ml-auto h-3.5 w-3.5 text-gray-400 shrink-0" />}
          </button>
        )}

        {TIER_LIST.map((t) => {
          const sel = selected.has(t.key);
          return (
            <button
              key={t.key}
              type="button"
              onClick={() => toggle(t.key)}
              className={cn(
                "w-full flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left transition-all duration-150",
                sel
                  ? "bg-gray-50 dark:bg-(--muted)"
                  : "hover:bg-gray-50/70 dark:hover:bg-(--muted)",
              )}
              style={sel ? { borderLeft: `2px solid ${t.color}`, paddingLeft: 8 } : undefined}
            >
              <span className="inline-block w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: t.color }} />
              <div className="flex-1 min-w-0">
                <span className={cn("text-xs font-medium", sel ? "text-gray-900 dark:text-gray-100" : "text-gray-600 dark:text-gray-300")}>
                  {t.label}
                </span>
                <span className="text-[10px] text-gray-400 ml-1.5">{t.desc}</span>
              </div>
              {sel && <Check className="h-3.5 w-3.5 shrink-0" style={{ color: t.color }} />}
            </button>
          );
        })}
      </PopoverContent>
    </Popover>
  );
}
