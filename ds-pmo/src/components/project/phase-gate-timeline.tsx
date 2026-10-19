"use client";

import { useTheme } from "next-themes";
import { getPhasesForLifecycle, getGatePositions, getVisiblePhaseCount, GATES } from "@/lib/constants";
import { formatDate } from "@/lib/utils";
import type { GateRecord } from "@/lib/db/models";

/* Gate positions and total are now lifecycle-aware — see getGatePositions() */

/** Wrapper: returns null instead of "—" for missing dates (used in timeline) */
function fmtDate(d: Date | string | null | undefined): string | null {
  if (!d) return null;
  return formatDate(d);
}

/* ── Diamond icon ────────────────────────────────────────────────── */
function GateDiamond({
  color,
  filled,
  size = 14,
  glow = false,
}: {
  color: string;
  filled: boolean;
  size?: number;
  glow?: boolean;
}) {
  return (
    <span
      className="inline-block shrink-0 transition-transform duration-200"
      style={{
        width: size,
        height: size,
        transform: "rotate(45deg)",
        backgroundColor: filled ? color : "var(--background)",
        border: `2px solid ${color}`,
        borderRadius: 2,
        boxShadow: glow
          ? `0 0 6px ${color}50, 0 0 14px ${color}20`
          : "0 1px 3px rgba(0,0,0,0.08)",
      }}
    />
  );
}

/* ── Main export ─────────────────────────────────────────────────── */
export function PhaseGateTimeline({
  currentPhaseKey,
  currentGateKey,
  gates,
  lifecycleType,
  onPhaseChange,
  onGateChange,
}: {
  currentPhaseKey: string;
  currentGateKey?: string | null;
  gates: GateRecord[];
  lifecycleType?: string | null;
  onPhaseChange?: (phaseKey: string) => void;
  onGateChange?: (gateKey: string) => void;
}) {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === "dark";
  const phases = getPhasesForLifecycle(lifecycleType);
  const TOTAL = getVisiblePhaseCount(lifecycleType); // phases excluding "Closed"
  const visiblePhases = phases.filter((p) => p.stageGroup !== "Closed");
  const currentPhaseNum =
    phases.find((p) => p.key === currentPhaseKey)?.phaseNumber ?? 0;
  const GATE_POSITIONS = getGatePositions(lifecycleType);

  // Build a gate lookup: key → { status, plannedDate, completedDate, color }
  const safeGates = gates ?? [];
  const gateMap = Object.fromEntries(
    GATES.map((def) => {
      const rec = safeGates.find((g) => g.gate === def.key);
      return [
        def.key,
        {
          key: def.key,
          color: def.color,
          status: rec?.status ?? "PLANNED",
          plannedDate: rec?.plannedDate ?? null,
          completedDate: rec?.completedDate ?? null,
        },
      ];
    }),
  );

  return (
    <div className="overflow-x-auto">
      <div style={{ minWidth: 720 }}>
        {/* ── Phase bar ──────────────────────────────────── */}
        <div className="relative">
          <div
            className="flex overflow-hidden"
            style={{ height: 48, borderRadius: 10, border: "1px solid var(--border)" }}
          >
            {visiblePhases.map((phase) => {
              const isActive = phase.key === currentPhaseKey;
              const isFuture = phase.phaseNumber > currentPhaseNum;
              const isLight = phase.key === "BENEFITS";

              let bg = phase.color;
              let fg = "#FFFFFF";
              if (isFuture) {
                bg = isDark ? "#282C34" : "#E5E7EB";
                fg = isDark ? "#6B7280" : "#9CA3AF";
              } else if (isLight) {
                bg = isDark ? "#282C34" : "#F9FAFB";
                fg = isDark ? "#D1D5DB" : "#374151";
              }

              return (
                <div
                  key={phase.key}
                  onClick={() => onPhaseChange?.(phase.key)}
                  className={`flex-1 flex flex-col items-center justify-center text-center relative transition-all duration-300 ${onPhaseChange ? "cursor-pointer hover:brightness-110" : ""}`}
                  style={{
                    backgroundColor: bg,
                    opacity: isFuture ? 0.5 : 1,
                  }}
                >
                  {/* Active indicator — subtle inner brightness, no harsh border */}
                  {isActive && (
                    <div
                      className="absolute inset-0 z-10 pointer-events-none"
                      style={{
                        background:
                          "linear-gradient(180deg, rgba(255,255,255,0.25) 0%, rgba(255,255,255,0) 60%)",
                        boxShadow: "inset 0 0 0 1.5px rgba(255,255,255,0.5)",
                      }}
                    />
                  )}
                  <span
                    className="text-[9px] font-bold tracking-[0.15em] leading-none"
                    style={{ color: fg, opacity: 0.55 }}
                  >
                    {phase.phaseNumber}
                  </span>
                  <span
                    className="text-[10.5px] font-semibold leading-tight mt-0.5 px-1"
                    style={{ color: fg }}
                  >
                    {phase.shortLabel}
                  </span>
                </div>
              );
            })}
          </div>

          {/* Orange caret below the active phase */}
          {(() => {
            const idx = visiblePhases.findIndex(
              (p) => p.key === currentPhaseKey,
            );
            if (idx < 0) return null;
            const pct = ((idx + 0.5) / TOTAL) * 100;
            return (
              <div
                className="absolute"
                style={{
                  left: `${pct}%`,
                  bottom: -6,
                  transform: "translateX(-50%)",
                  width: 0,
                  height: 0,
                  borderLeft: "5px solid transparent",
                  borderRight: "5px solid transparent",
                  borderTop: "5px solid #F97316",
                }}
              />
            );
          })()}
        </div>

        {/* ── Gate diamonds ─────────────────────────────── */}
        <div className="relative" style={{ height: 58, marginTop: 20 }}>
          {/* Thin horizontal rail */}
          <div
            className="absolute bg-gray-200/60 dark:bg-gray-600/40"
            style={{
              left: `${(GATE_POSITIONS[0].at / TOTAL) * 100}%`,
              right: `${100 - (GATE_POSITIONS[GATE_POSITIONS.length - 1].at / TOTAL) * 100}%`,
              top: 7,
              height: 1,
            }}
          />

          {GATE_POSITIONS.map(({ key, at }) => {
            const gate = gateMap[key];
            if (!gate) return null;
            const isWhite = key === "WHITE";
            const color = isWhite ? "#9CA3AF" : gate.color;
            const isPassed = gate.status === "PASSED";
            const isCurrent = currentGateKey === key;
            const leftPct = (at / TOTAL) * 100;

            const dateStr = isPassed
              ? fmtDate(gate.completedDate)
              : fmtDate(gate.plannedDate);

            return (
              <div
                key={key}
                onClick={() => onGateChange?.(key)}
                className={`absolute flex flex-col items-center group ${onGateChange ? "cursor-pointer" : "cursor-default"}`}
                style={{
                  left: `${leftPct}%`,
                  transform: "translateX(-50%)",
                  top: 0,
                }}
              >
                {/* Vertical tick */}
                <div
                  className="absolute bg-gray-200 dark:bg-gray-600"
                  style={{
                    width: 1,
                    height: 20,
                    top: -20,
                    left: "50%",
                    transform: "translateX(-50%)",
                  }}
                />

                {/* Diamond with hover scale */}
                <div className={`transition-transform duration-200 group-hover:scale-125 ${isCurrent ? "scale-125" : ""}`}>
                  <GateDiamond
                    color={color}
                    filled={isPassed}
                    size={isCurrent ? 15 : 13}
                    glow={isPassed}
                  />
                </div>

                {/* Label */}
                <span
                  className={`text-[8px] font-bold uppercase tracking-wider mt-1.5 whitespace-nowrap transition-colors duration-200 group-hover:brightness-125 ${isCurrent ? "underline underline-offset-2" : ""}`}
                  style={{ color }}
                >
                  {key}
                </span>

                {/* Date */}
                {dateStr && (
                  <span
                    className={`text-[7.5px] font-medium mt-px whitespace-nowrap ${
                      isPassed ? "text-green-600 dark:text-green-400" : "text-gray-400 dark:text-gray-500"
                    }`}
                  >
                    {dateStr}
                  </span>
                )}

                {/* Hover tooltip */}
                <div
                  className="absolute bottom-full mb-3 px-2.5 py-1.5 rounded-md bg-gray-900 text-white text-[10px] whitespace-nowrap
                             opacity-0 pointer-events-none translate-y-1 group-hover:opacity-100 group-hover:translate-y-0
                             transition-all duration-200 z-30 shadow-lg"
                >
                  <div className="font-semibold">
                    {key.charAt(0) + key.slice(1).toLowerCase()} Gate
                  </div>
                  <div className="text-gray-300 mt-0.5">
                    {isPassed
                      ? `Passed ${dateStr ?? ""}`
                      : dateStr
                      ? `Planned ${dateStr}`
                      : "Planned"}
                  </div>
                  {/* Tooltip arrow */}
                  <div
                    className="absolute left-1/2 -bottom-1 -translate-x-1/2 w-2 h-2 bg-gray-900 rotate-45"
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
