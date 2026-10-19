import { describe, expect, it } from "vitest";
import {
  getPhasesForLifecycleFilter,
  normalizeLifecycleFilter,
  phasesValidForLifecycle,
} from "@/lib/lifecycle-filter";

describe("lifecycle portfolio filters", () => {
  it("maps only persisted lifecycle values to an API filter", () => {
    expect(normalizeLifecycleFilter("ENGINEERING")).toBe("ENGINEERING");
    expect(normalizeLifecycleFilter("IT")).toBe("IT");
    expect(normalizeLifecycleFilter("GLOBAL")).toBeUndefined();
    expect(normalizeLifecycleFilter("invalid")).toBeUndefined();
    expect(normalizeLifecycleFilter(null)).toBeUndefined();
  });

  it("builds Global as a de-duplicated union of EE and IT phases", () => {
    const keys = getPhasesForLifecycleFilter("GLOBAL").map((phase) => phase.key);
    expect(keys).toContain("DETAILED_DESIGN");
    expect(keys).toContain("DESIGN");
    expect(keys).toContain("REALISATION");
    expect(new Set(keys).size).toBe(keys.length);
    expect(keys.filter((key) => key === "IDEATION")).toHaveLength(1);
  });

  it("removes phases that are incompatible with a selected lifecycle", () => {
    expect(
      phasesValidForLifecycle(["IDEATION", "DETAILED_DESIGN", "REALISATION"], "IT"),
    ).toEqual(["IDEATION", "REALISATION"]);
    expect(phasesValidForLifecycle(["DETAILED_DESIGN"], "IT")).toBeUndefined();
  });

  it("keeps phase selections unchanged for Global", () => {
    const phases = ["DETAILED_DESIGN", "REALISATION"];
    expect(phasesValidForLifecycle(phases, "GLOBAL")).toBe(phases);
  });
});
