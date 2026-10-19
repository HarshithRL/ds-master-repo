"use client";

import { useState, useMemo } from "react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { PROJECT_FLAGS, type ProjectFlagKey } from "@/lib/constants";
import { cn } from "@/lib/utils";
import { ChevronDown, Check } from "lucide-react";

interface FlagPickerProps {
  value: ProjectFlagKey[];
  onChange: (next: ProjectFlagKey[]) => void;
  disabled?: boolean;
}

export function FlagPicker({ value, onChange, disabled }: FlagPickerProps) {
  const [open, setOpen] = useState(false);

  const selected = useMemo(() => new Set(value), [value]);
  const isEmpty = selected.size === 0;

  if (disabled) {
    const labels = PROJECT_FLAGS.filter((f) => selected.has(f.key)).map((f) => f.label);
    return (
      <div className="form-control-readonly text-sm">
        {labels.length > 0 ? (
          <span className="truncate">{labels.join(", ")}</span>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </div>
    );
  }

  const toggle = (key: ProjectFlagKey) => {
    const next = new Set(selected);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    onChange([...next] as ProjectFlagKey[]);
  };

  const triggerLabel = (() => {
    if (isEmpty) return null;
    if (selected.size === 1) {
      const f = PROJECT_FLAGS.find((f) => selected.has(f.key));
      return f?.label ?? null;
    }
    return `${selected.size} selected`;
  })();

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn(
            "form-control w-full flex items-center gap-2 text-left transition-all h-9 text-sm",
            !isEmpty && "ring-1 ring-etex-orange/20 border-etex-orange/30",
          )}
        >
          {triggerLabel ? (
            <span className="truncate font-medium text-gray-900 dark:text-gray-100">
              {triggerLabel}
            </span>
          ) : (
            <span className="text-gray-400 dark:text-gray-500 truncate">Select…</span>
          )}
          <ChevronDown
            className={cn(
              "ml-auto shrink-0 text-gray-400 dark:text-gray-500 transition-transform duration-200 h-3.5 w-3.5",
              open && "rotate-180",
            )}
          />
        </button>
      </PopoverTrigger>

      <PopoverContent
        align="start"
        className="w-(--radix-popover-trigger-width) min-w-56 p-0 overflow-hidden shadow-xl border border-gray-200/80 dark:border-(--border) rounded-lg dark:shadow-[0_8px_24px_rgba(0,0,0,0.4)]"
      >
        <div className="max-h-60 overflow-y-auto p-1.5">
          {PROJECT_FLAGS.map((f) => {
            const sel = selected.has(f.key);
            return (
              <button
                key={f.key}
                type="button"
                onClick={() => toggle(f.key)}
                title={f.hint}
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
                    "text-xs font-medium flex-1 truncate",
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
      </PopoverContent>
    </Popover>
  );
}
