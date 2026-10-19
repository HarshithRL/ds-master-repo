import { Suspense } from "react";
import { ExecutiveDashboard } from "@/components/dashboard/executive-dashboard";
import { DashboardSkeleton } from "@/components/dashboard/dashboard-skeleton";

export default function DashboardPage() {
  return (
    <Suspense fallback={<DashboardSkeleton />}>
      <ExecutiveDashboard />
    </Suspense>
  );
}
