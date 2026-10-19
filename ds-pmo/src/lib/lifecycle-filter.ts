import { getPhasesForLifecycle, LIFECYCLE_TYPES, type Phase } from "@/lib/constants";

export const LIFECYCLE_FILTER_OPTIONS = [
  { key: "GLOBAL", label: "Global" },
  { key: "ENGINEERING", label: "EE" },
  { key: "IT", label: "IT" },
] as const;

export type LifecycleFilterValue = (typeof LIFECYCLE_FILTER_OPTIONS)[number]["key"];
export type PersistedLifecycleFilter = Exclude<LifecycleFilterValue, "GLOBAL">;

/** Global is represented by no API/URL filter so existing links keep showing both lifecycles. */
export function normalizeLifecycleFilter(
  value?: string | null,
): PersistedLifecycleFilter | undefined {
  return value === "ENGINEERING" || value === "IT" ? value : undefined;
}

/** Return one lifecycle's phases, or a de-duplicated union for Global. */
export function getPhasesForLifecycleFilter(value: LifecycleFilterValue): Phase[] {
  if (value !== "GLOBAL") return getPhasesForLifecycle(value);
  const phases = new Map<string, Phase>();
  for (const lifecycle of LIFECYCLE_TYPES) {
    for (const phase of getPhasesForLifecycle(lifecycle.key)) {
      if (!phases.has(phase.key)) phases.set(phase.key, phase);
    }
  }
  return [...phases.values()];
}

/** Drop phase selections that do not exist in the newly selected lifecycle. */
export function phasesValidForLifecycle(
  phases: string[] | undefined,
  lifecycle: LifecycleFilterValue,
): string[] | undefined {
  if (!phases?.length || lifecycle === "GLOBAL") return phases;
  const validKeys = new Set(getPhasesForLifecycleFilter(lifecycle).map((phase) => phase.key));
  const validPhases = phases.filter((phase) => validKeys.has(phase));
  return validPhases.length ? validPhases : undefined;
}
