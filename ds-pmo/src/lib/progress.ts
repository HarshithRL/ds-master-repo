/**
 * Centralized project progress calculation.
 *
 * Post-Grey (execution): time elapsed since Grey completion relative to White planned date.
 * Pre-Grey (development): time elapsed since last passed gate relative to next planned gate.
 *
 * All values are percentages 0-100, capped at 100.
 */

import { GATE_KEYS } from "@/lib/constants";

// Canonical lifecycle order — same as GATE_KEYS in constants. Re-aliased here
// so the progress functions read naturally without renaming everything.
const GATE_ORDER = GATE_KEYS;

const MS_PER_DAY = 1000 * 60 * 60 * 24;

interface GateInput {
  gate: string;
  status: string;
  plannedDate: Date | string | null;
  completedDate: Date | string | null;
}

/**
 * Progress through all 8 lifecycle gates up to the next upcoming gate (0–100).
 * Counts how many leading gates are PASSED in canonical order and returns
 * passed / total × 100. Used by the projects table summary and the live
 * dashboard summary aggregation.
 */
export function computeUntilNextGate(gates: { gate: string; status: string }[]): number {
  if (!gates?.length) return 0;
  const map = new Map(gates.map((g) => [g.gate, g.status]));
  let passed = 0;
  for (const g of GATE_KEYS) {
    if (map.get(g) === "PASSED") passed++;
    else break;
  }
  return Math.round((passed / GATE_KEYS.length) * 100);
}

function toTime(d: Date | string | null): number | null {
  if (!d) return null;
  const ms = typeof d === "string" ? new Date(d).getTime() : d.getTime();
  return Number.isNaN(ms) ? null : ms;
}

/**
 * Days between the GREEN and WHITE gate planned dates — the planned execution
 * window. Returns null if either gate has no planned date. Used as the SVAC
 * denominator (schedule float as % of remaining execution duration).
 */
export function computeDaysGreenToWhite(gates: GateInput[]): number | null {
  if (!gates || gates.length === 0) return null;
  const map = new Map(gates.map((g) => [g.gate, g]));
  const green = toTime(map.get("GREEN")?.plannedDate ?? null);
  const white = toTime(map.get("WHITE")?.plannedDate ?? null);
  if (green == null || white == null) return null;
  const diff = white - green;
  if (diff <= 0) return null;
  return Math.round(diff / MS_PER_DAY);
}

/**
 * Compute project progress from gate records.
 *
 * @returns percentage 0–100 (integer)
 */
export function computeProgress(gates: GateInput[]): number {
  if (!gates || gates.length === 0) return 0;

  const gateMap = new Map(gates.map((g) => [g.gate, g]));
  const now = Date.now();

  const grey = gateMap.get("GREY");
  const greyPassed = grey?.status === "PASSED";

  if (greyPassed) {
    // ── Post-Grey: (today − grey.completedDate) / (white.plannedDate − grey.completedDate) ──
    const greyCompleted = toTime(grey.completedDate);
    if (!greyCompleted) return 0;

    const white = gateMap.get("WHITE");
    const whitePlanned = toTime(white?.plannedDate ?? null);
    if (!whitePlanned) return 0;

    const total = whitePlanned - greyCompleted;
    if (total <= 0) return 100;

    const elapsed = now - greyCompleted;
    const pct = Math.round((elapsed / total) * 100);
    return Math.max(0, Math.min(100, pct));
  }

  // ── Pre-Grey: (today − lastPassed.completedDate) / (nextPlanned.plannedDate − lastPassed.completedDate) ──
  let lastPassedTime: number | null = null;
  let nextPlannedTime: number | null = null;

  for (const key of GATE_ORDER) {
    const g = gateMap.get(key);
    if (!g) continue;

    if (g.status === "PASSED") {
      const t = toTime(g.completedDate);
      if (t) lastPassedTime = t;
    } else {
      // First non-passed gate with a planned date is the target
      const t = toTime(g.plannedDate);
      if (t) {
        nextPlannedTime = t;
        break;
      }
    }
  }

  // No passed gates yet — fall back to next planned gate only
  if (lastPassedTime == null) {
    // No reference point → 0%
    return 0;
  }

  if (nextPlannedTime == null) {
    // All gates passed or no planned dates → 100%
    return 100;
  }

  const total = nextPlannedTime - lastPassedTime;
  if (total <= 0) return 100;

  const elapsed = now - lastPassedTime;
  const pct = Math.round((elapsed / total) * 100);
  return Math.max(0, Math.min(100, pct));
}
