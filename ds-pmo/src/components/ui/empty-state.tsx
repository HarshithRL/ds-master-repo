import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Consistent "no data" placeholder. Use across tables, lists, and section
 * bodies where there's nothing yet to show. Keep messaging short — describe
 * *what's missing*, not "no results".
 */
export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  size = "default",
  className,
}: {
  icon?: LucideIcon;
  title: string;
  description?: string;
  action?: React.ReactNode;
  size?: "compact" | "default";
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center",
        size === "compact" ? "py-6 px-4" : "py-12 px-6",
        className,
      )}
    >
      {Icon && (
        <div
          className={cn(
            "rounded-full bg-etex-gray-100 dark:bg-etex-gray-800 flex items-center justify-center mb-3",
            size === "compact" ? "w-10 h-10" : "w-14 h-14",
          )}
        >
          <Icon
            className={cn(
              "text-etex-gray-400 dark:text-etex-gray-500",
              size === "compact" ? "w-5 h-5" : "w-7 h-7",
            )}
            strokeWidth={1.6}
          />
        </div>
      )}
      <div
        className={cn(
          "font-semibold text-etex-charcoal dark:text-etex-gray-100",
          size === "compact" ? "text-sm" : "text-base",
        )}
      >
        {title}
      </div>
      {description && (
        <p
          className={cn(
            "text-etex-gray-500 dark:text-etex-gray-400 mt-1 max-w-md",
            size === "compact" ? "text-xs" : "text-sm",
          )}
        >
          {description}
        </p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
