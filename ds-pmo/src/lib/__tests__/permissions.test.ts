import {
  sessionHasPermission,
  sessionHasAnyPermission,
  ALL_PERMISSIONS,
  type Permission,
} from "../permissions";

// ─── sessionHasPermission ─────────────────────────────────────────

describe("sessionHasPermission", () => {
  it("returns false when sessionUser is null", () => {
    expect(sessionHasPermission(null, "MANAGE_USERS")).toBe(false);
  });

  it("returns false when sessionUser is undefined", () => {
    expect(sessionHasPermission(undefined, "MANAGE_USERS")).toBe(false);
  });

  it("returns false when permissions is undefined", () => {
    expect(sessionHasPermission({}, "MANAGE_USERS")).toBe(false);
  });

  it("returns false when permissions is empty", () => {
    expect(sessionHasPermission({ permissions: [] }, "MANAGE_USERS")).toBe(
      false,
    );
  });

  it("returns false when permission is not in the array", () => {
    expect(
      sessionHasPermission(
        { permissions: ["MANAGE_FACTORIES"] },
        "MANAGE_USERS",
      ),
    ).toBe(false);
  });

  it("returns true when permission is in the array", () => {
    expect(
      sessionHasPermission(
        { permissions: ["MANAGE_USERS", "MANAGE_FACTORIES"] },
        "MANAGE_USERS",
      ),
    ).toBe(true);
  });

  it("returns true for any permission when user is ADMIN globalRole", () => {
    expect(
      sessionHasPermission(
        { permissions: [], globalRole: "ADMIN" },
        "MANAGE_USERS",
      ),
    ).toBe(true);
    expect(
      sessionHasPermission(
        { permissions: [], globalRole: "ADMIN" },
        "VIEW_AUDIT_LOGS",
      ),
    ).toBe(true);
  });

  it("is case-sensitive", () => {
    expect(
      sessionHasPermission(
        { permissions: ["manage_users"] },
        "MANAGE_USERS",
      ),
    ).toBe(false);
  });

  it("works for every defined permission", () => {
    const user = { permissions: [...ALL_PERMISSIONS] };
    for (const perm of ALL_PERMISSIONS) {
      expect(sessionHasPermission(user, perm)).toBe(true);
    }
  });
});

// ─── sessionHasAnyPermission ──────────────────────────────────────

describe("sessionHasAnyPermission", () => {
  it("returns false for null user", () => {
    expect(sessionHasAnyPermission(null)).toBe(false);
  });

  it("returns false for undefined user", () => {
    expect(sessionHasAnyPermission(undefined)).toBe(false);
  });

  it("returns false for user with undefined permissions", () => {
    expect(sessionHasAnyPermission({})).toBe(false);
  });

  it("returns false for user with empty permissions", () => {
    expect(sessionHasAnyPermission({ permissions: [] })).toBe(false);
  });

  it("returns true for user with at least one permission", () => {
    expect(
      sessionHasAnyPermission({ permissions: ["VIEW_AUDIT_LOGS"] }),
    ).toBe(true);
  });

  it("returns true for user with multiple permissions", () => {
    expect(
      sessionHasAnyPermission({
        permissions: ["MANAGE_USERS", "MANAGE_FACTORIES"],
      }),
    ).toBe(true);
  });

  it("returns true for ADMIN globalRole even with no explicit permissions", () => {
    expect(
      sessionHasAnyPermission({ permissions: [], globalRole: "ADMIN" }),
    ).toBe(true);
  });
});

// ─── ALL_PERMISSIONS constant ─────────────────────────────────────

describe("ALL_PERMISSIONS", () => {
  it("contains exactly 6 admin permissions", () => {
    expect(ALL_PERMISSIONS).toHaveLength(6);
  });

  it("includes all expected permissions", () => {
    const expected: Permission[] = [
      "MANAGE_USERS",
      "MANAGE_FACTORIES",
      "MANAGE_CATEGORIES",
      "MANAGE_DIVISIONS",
      "VIEW_AUDIT_LOGS",
      "MANAGE_RESOURCES",
    ];
    expect(ALL_PERMISSIONS).toEqual(expect.arrayContaining(expected));
  });
});
