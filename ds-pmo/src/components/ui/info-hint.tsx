"use client";

import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { Info } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * InfoHint — a subtle info icon that reveals a white popover on hover.
 * Shows the field name as a title with the description underneath.
 */
export function InfoHint({
  label,
  text,
  className,
  side = "top",
}: {
  /** Field name shown as the popover title */
  label?: string;
  /** Explanation / description shown under the title */
  text: string;
  className?: string;
  side?: "top" | "right" | "bottom" | "left";
}) {
  return (
    <TooltipPrimitive.Provider delayDuration={200} skipDelayDuration={100}>
      <TooltipPrimitive.Root>
        <TooltipPrimitive.Trigger asChild>
          <span
            className={cn(
              "inline-flex items-center justify-center w-3.5 h-3.5 rounded-full cursor-pointer",
              "text-gray-300 hover:text-etex-orange transition-colors duration-150",
              className,
            )}
            tabIndex={-1}
          >
            <Info size={11} strokeWidth={2.5} />
          </span>
        </TooltipPrimitive.Trigger>
        <TooltipPrimitive.Portal>
          <TooltipPrimitive.Content
            side={side}
            sideOffset={6}
            className={cn(
              "z-[100] max-w-60 rounded-lg",
              "bg-white shadow-lg shadow-black/8 ring-1 ring-gray-200",
              "select-none",
              "animate-in fade-in-0 zoom-in-95 duration-150",
              "data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95 data-[state=closed]:duration-100",
              "data-[side=bottom]:slide-in-from-top-1",
              "data-[side=left]:slide-in-from-right-1",
              "data-[side=right]:slide-in-from-left-1",
              "data-[side=top]:slide-in-from-bottom-1",
            )}
          >
            <div className="px-3 py-2.5">
              {label && (
                <div className="text-[11px] font-semibold text-gray-900 mb-0.5 flex items-center gap-1.5">
                  <span className="inline-block w-1 h-1 rounded-full bg-etex-orange shrink-0" />
                  {label}
                </div>
              )}
              <p className={cn(
                "text-[11.5px] leading-normal text-gray-500 font-normal tracking-normal",
                label && "pl-2.5",
              )}>
                {text}
              </p>
            </div>
            <TooltipPrimitive.Arrow className="fill-white drop-shadow-sm" width={10} height={5} />
          </TooltipPrimitive.Content>
        </TooltipPrimitive.Portal>
      </TooltipPrimitive.Root>
    </TooltipPrimitive.Provider>
  );
}
