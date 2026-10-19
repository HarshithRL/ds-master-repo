"use client";

import { memo } from "react";
import { PropLabel } from "@/components/ui/auto-fields";
import { getPhaseByKey } from "@/lib/constants";

export const ProgressWheel = memo(function ProgressWheel({
  value,
  phase,
}: {
  value: number;
  phase: ReturnType<typeof getPhaseByKey>;
}) {
  const pct = Math.min(100, Math.max(0, value));
  const size = 36;
  const r = 13;
  const stroke = 3.5;
  const circ = 2 * Math.PI * r;
  const offset = circ - (pct / 100) * circ;
  const accentColor = phase?.color ?? "#F97316";

  return (
    <div className="shrink-0">
      <PropLabel hint="Auto-calculated from gate dates">Progress</PropLabel>
      <div className="flex items-center gap-2 h-9">
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="shrink-0">
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" className="ring-track" strokeWidth={stroke} />
          <circle
            cx={size / 2} cy={size / 2} r={r}
            fill="none"
            stroke={accentColor}
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={circ}
            strokeDashoffset={offset}
            style={{ transform: "rotate(-90deg)", transformOrigin: `${size / 2}px ${size / 2}px`, transition: "stroke-dashoffset 500ms ease, stroke 300ms ease" }}
          />
        </svg>
        <span className="text-sm font-mono tabular-nums font-medium">{pct}%</span>
      </div>
    </div>
  );
});
