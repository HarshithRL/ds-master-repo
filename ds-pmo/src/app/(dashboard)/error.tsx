"use client";

import { useEffect } from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";

/**
 * Route-level error boundary for the (dashboard) segment. Catches unexpected
 * runtime errors in any nested page and shows a clean recovery UI.
 */
export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Dashboard route error:", error);
  }, [error]);

  return (
    <div className="flex items-center justify-center min-h-[60vh] p-6">
      <div className="card-compact max-w-md w-full p-8 text-center">
        <div className="w-14 h-14 rounded-full bg-red-50 dark:bg-red-950/40 flex items-center justify-center mx-auto mb-4">
          <AlertTriangle className="w-7 h-7 text-red-600 dark:text-red-400" strokeWidth={1.8} />
        </div>
        <h2 className="text-lg font-semibold text-etex-charcoal dark:text-etex-gray-100">
          Something went wrong loading this page.
        </h2>
        <p className="text-sm text-etex-gray-500 dark:text-etex-gray-400 mt-2">
          {error.message?.slice(0, 200) || "An unexpected error occurred."}
        </p>
        {error.digest && (
          <p className="text-[10px] text-etex-gray-400 mt-2 font-mono">ref: {error.digest}</p>
        )}
        <div className="mt-5 flex items-center justify-center gap-2">
          <Button onClick={() => reset()} className="bg-etex-orange hover:bg-etex-orange/90 text-white">
            <RotateCcw size={14} className="mr-1.5" />
            Try again
          </Button>
          <Button asChild variant="outline">
            <a href="/dashboard">Back to dashboard</a>
          </Button>
        </div>
      </div>
    </div>
  );
}
