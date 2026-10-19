import { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface PageHeaderProps {
  title: string;
  subtitle?: string;
  children?: ReactNode;
  className?: string;
}

export function PageHeader({ title, subtitle, children, className }: PageHeaderProps) {
  return (
    <div className={cn("mb-6 flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 sm:gap-4", className)}>
      <div className="min-w-0">
        <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100 tracking-tight leading-tight">
          {title}
        </h1>
        {subtitle && (
          <p className="mt-0.5 text-sm text-gray-500 dark:text-gray-400">{subtitle}</p>
        )}
      </div>
      {children && (
        <div className="flex items-center gap-2 flex-shrink-0">{children}</div>
      )}
    </div>
  );
}
