"use client";

import { Check, AlertCircle, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { SaveStatus } from "@/hooks/use-save-status";

export function SaveIndicator({ status }: { status: SaveStatus }) {
  const isIdle = status === "idle";

  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "fixed bottom-6 right-6 z-50",
        "inline-flex items-center gap-2 px-3.5 py-2",
        "rounded-md border shadow-lg backdrop-blur",
        "text-sm font-medium",
        "transition-all duration-200 ease-out",
        isIdle
          ? "opacity-0 translate-y-2 pointer-events-none"
          : "opacity-100 translate-y-0",
        status === "saving" &&
          "text-gray-700 dark:text-gray-200 bg-white/95 dark:bg-[#21252B]/95 border-gray-300 dark:border-[#3D4350]",
        status === "saved" &&
          "text-green-700 dark:text-green-300 bg-green-50/95 dark:bg-green-500/15 border-green-300 dark:border-green-500/40",
        status === "error" &&
          "text-red-700 dark:text-red-300 bg-red-50/95 dark:bg-red-500/15 border-red-300 dark:border-red-500/40",
      )}
    >
      {status === "saving" && (
        <>
          <Loader2 className="h-4 w-4 shrink-0 animate-spin" aria-hidden />
          <span>Saving…</span>
        </>
      )}
      {status === "saved" && (
        <>
          <Check className="h-4 w-4 shrink-0 stroke-[2.5]" aria-hidden />
          <span>Saved</span>
        </>
      )}
      {status === "error" && (
        <>
          <AlertCircle className="h-4 w-4 shrink-0" aria-hidden />
          <span>Save failed</span>
        </>
      )}
    </div>
  );
}
