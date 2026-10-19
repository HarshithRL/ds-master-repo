import { createProjectSchema, updateProjectSchema } from "../validations";

// ─── project reference ────────────────────────────────────────────
//
// A blank reference has no real value, so it should be stored as NULL, not
// as "" (a distinct, meaningless value). Ported from the upstream fix for a
// UNIQUE-index collision under Postgres — Delta has no unique constraints,
// so that specific failure mode doesn't apply here, but null-for-"no
// reference" is still the correct representation.

describe("project reference normalisation", () => {
  const base = { name: "Test project" };

  it("folds an empty reference to null on create", () => {
    const parsed = createProjectSchema.parse({ ...base, reference: "" });
    expect(parsed.reference).toBeNull();
  });

  it("folds a whitespace-only reference to null on create", () => {
    const parsed = createProjectSchema.parse({ ...base, reference: "   " });
    expect(parsed.reference).toBeNull();
  });

  it("keeps a real reference, trimmed", () => {
    const parsed = createProjectSchema.parse({ ...base, reference: "  CCNG-1  " });
    expect(parsed.reference).toBe("CCNG-1");
  });

  it("leaves an omitted reference undefined so it is not written", () => {
    const parsed = createProjectSchema.parse(base);
    expect(parsed.reference).toBeUndefined();
  });

  it("folds an empty reference to null on update too", () => {
    // Clearing the field in the edit form must not plant a fresh ''.
    const parsed = updateProjectSchema.parse({ reference: "" });
    expect(parsed.reference).toBeNull();
  });

  it("passes an explicit null through on update", () => {
    const parsed = updateProjectSchema.parse({ reference: null });
    expect(parsed.reference).toBeNull();
  });
});
