import { Skeleton } from "@/components/ui/skeleton";

function CompactWidgetSkeleton() {
  return (
    <div className="card-compact p-4">
      <Skeleton className="h-3 w-24 mb-4" />
      <div className="space-y-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="space-y-1.5">
            <div className="flex justify-between">
              <Skeleton className="h-3 w-20" />
              <Skeleton className="h-3 w-12" />
            </div>
            <Skeleton className="h-4 w-full rounded-sm" />
          </div>
        ))}
      </div>
    </div>
  );
}

export function DashboardSkeleton() {
  return (
    <div className="space-y-4 sm:space-y-6 animate-page-enter">
      {/* Header */}
      <div>
        <Skeleton className="h-6 w-48" />
        <Skeleton className="mt-1 h-4 w-64" />
      </div>

      {/* KPI strip */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="card-compact p-5">
            <Skeleton className="h-2.5 w-20 mb-3" />
            <Skeleton className="h-7 w-16 mb-2" />
            <Skeleton className="h-2.5 w-28" />
          </div>
        ))}
      </div>

      {/* Budget + CPI/SPI */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
        {/* Budget Performance skeleton */}
        <div className="section-card overflow-hidden">
          <div className="section-header flex justify-between">
            <Skeleton className="h-4 w-32 bg-white/20" />
            <Skeleton className="h-4 w-16 bg-white/20" />
          </div>
          <div className="p-4 space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="space-y-1.5">
                <div className="flex justify-between">
                  <div className="flex items-baseline gap-1.5">
                    <Skeleton className="h-3 w-10" />
                    <Skeleton className="h-2.5 w-24" />
                  </div>
                  <Skeleton className="h-3 w-14" />
                </div>
                <Skeleton className="h-5 w-full rounded-sm" />
              </div>
            ))}
          </div>
        </div>

        {/* CPI/SPI skeleton */}
        <div className="section-card overflow-hidden">
          <div className="section-header flex justify-between">
            <Skeleton className="h-4 w-24 bg-white/20" />
            <div className="flex gap-2">
              <Skeleton className="h-3 w-16 bg-white/20" />
              <Skeleton className="h-3 w-16 bg-white/20" />
              <Skeleton className="h-3 w-16 bg-white/20" />
            </div>
          </div>
          <div className="p-4">
            <Skeleton className="h-75 w-full rounded" />
            <Skeleton className="mt-3 h-9 w-full rounded-md" />
          </div>
        </div>
      </div>

      {/* Distribution charts */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <CompactWidgetSkeleton key={i} />
        ))}
      </div>

      {/* Schedule adherence */}
      <div className="section-card overflow-hidden">
        <div className="section-header">
          <Skeleton className="h-4 w-40 bg-white/20" />
        </div>
        <div className="p-4 space-y-3">
          <Skeleton className="h-7 w-full rounded" />
          <div className="flex flex-wrap gap-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-3 w-20" />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
