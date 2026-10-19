import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { createMockRequest, mockSessionUser } from "./helpers";

// ─── Mocks ────────────────────────────────────────────────────────

vi.mock("@/lib/current-user", () => ({
  getCurrentUserFromRequest: vi.fn(),
}));

vi.mock("@/lib/rate-limit", () => ({
  checkRateLimit: vi.fn().mockReturnValue(true),
  RATE_LIMITS: {
    read: { key: "read", limit: 100, windowMs: 60_000 },
    mutation: { key: "mutation", limit: 30, windowMs: 60_000 },
  },
}));

// Also mock audit — re-exported by api-handler
vi.mock("@/lib/audit", () => ({
  createAuditLog: vi.fn(),
  diffObjects: vi.fn(),
}));

// Identity/pure checks (src/lib/permissions.ts) stay real; the DB-backed
// project-access checks (src/lib/access-control.ts) are mocked, since they
// hit src/lib/db/* under the hood, which needs a live warehouse.
vi.mock("../access-control", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../access-control")>();
  return {
    ...actual,
    canViewProject: vi.fn(),
    canEditProject: vi.fn(),
    whyCantEditProject: vi.fn().mockResolvedValue("cannot edit"),
    whyCantViewProject: vi.fn().mockResolvedValue("cannot view"),
  };
});

import { getCurrentUserFromRequest } from "@/lib/current-user";
import { checkRateLimit } from "@/lib/rate-limit";
import { canViewProject, canEditProject } from "../access-control";
import { ConflictError, NotFoundError } from "../db/errors";
import { withHandler } from "../api-handler";

const mockGetCurrentUser = getCurrentUserFromRequest as ReturnType<typeof vi.fn>;
const mockCheckRateLimit = checkRateLimit as ReturnType<typeof vi.fn>;
const mockCanViewProject = canViewProject as ReturnType<typeof vi.fn>;
const mockCanEditProject = canEditProject as ReturnType<typeof vi.fn>;

// Helper to call a handler with default params
function callHandler(
  handler: ReturnType<typeof withHandler>,
  req: NextRequest,
  params: Record<string, string> = {},
) {
  return handler(req, { params: Promise.resolve(params) as any });
}

// ─── Rate Limiting ────────────────────────────────────────────────

describe("withHandler — rate limiting", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetCurrentUser.mockResolvedValue(mockSessionUser());
    mockCheckRateLimit.mockReturnValue(true);
  });

  it("returns 429 when rate limit is exceeded", async () => {
    mockCheckRateLimit.mockReturnValue(false);

    const handler = withHandler(
      { rateLimit: { key: "test", limit: 1, windowMs: 60_000 } },
      async () => NextResponse.json({ ok: true }),
    );

    const res = await callHandler(handler, createMockRequest({}));
    expect(res.status).toBe(429);
    expect(res.headers.get("Retry-After")).toBe("60");

    const body = await res.json();
    expect(body.error).toContain("Too many requests");
  });

  it("proceeds normally when rate limit passes", async () => {
    const handler = withHandler(
      { rateLimit: { key: "test", limit: 100, windowMs: 60_000 } },
      async () => NextResponse.json({ ok: true }),
    );

    const res = await callHandler(handler, createMockRequest({}));
    expect(res.status).toBe(200);
  });

  it("extracts IP from x-forwarded-for for rate limit identifier", async () => {
    const handler = withHandler(
      { rateLimit: { key: "test", limit: 100, windowMs: 60_000 } },
      async () => NextResponse.json({ ok: true }),
    );

    await callHandler(
      handler,
      createMockRequest({ headers: { "x-forwarded-for": "10.0.0.1, 10.0.0.2" } }),
    );

    expect(mockCheckRateLimit).toHaveBeenCalledWith(
      expect.any(Object),
      "10.0.0.1",
    );
  });

  it("does not check rate limit when config omits rateLimit", async () => {
    const handler = withHandler(
      {},
      async () => NextResponse.json({ ok: true }),
    );

    await callHandler(handler, createMockRequest({}));
    expect(mockCheckRateLimit).not.toHaveBeenCalled();
  });
});

// ─── Authentication ───────────────────────────────────────────────
// Identity now comes from getCurrentUserFromRequest (reads the Databricks
// Apps forwarded-identity header) instead of a NextAuth session.

describe("withHandler — authentication", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockCheckRateLimit.mockReturnValue(true);
  });

  it("returns 401 when getCurrentUserFromRequest returns null", async () => {
    mockGetCurrentUser.mockResolvedValue(null);

    const handler = withHandler(
      {},
      async () => NextResponse.json({ ok: true }),
    );

    const res = await callHandler(handler, createMockRequest({}));
    expect(res.status).toBe(401);

    const body = await res.json();
    expect(body.error).toBe("Unauthorized");
  });

  it("proceeds when a valid user resolves", async () => {
    mockGetCurrentUser.mockResolvedValue(mockSessionUser());

    const handler = withHandler(
      {},
      async () => NextResponse.json({ ok: true }),
    );

    const res = await callHandler(handler, createMockRequest({}));
    expect(res.status).toBe(200);
  });

  it("skips auth check when config.auth is false", async () => {
    mockGetCurrentUser.mockResolvedValue(null);

    const handler = withHandler(
      { auth: false },
      async () => NextResponse.json({ ok: true }),
    );

    const res = await callHandler(handler, createMockRequest({}));
    expect(res.status).toBe(200);
    // getCurrentUserFromRequest should not gate this — handler bypasses it
    expect(mockGetCurrentUser).not.toHaveBeenCalled();
  });
});

// ─── Permission Checks ───────────────────────────────────────────

describe("withHandler — permissions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockCheckRateLimit.mockReturnValue(true);
  });

  it("returns 403 when user lacks required permission", async () => {
    mockGetCurrentUser.mockResolvedValue(mockSessionUser({ permissions: [] }));

    const handler = withHandler(
      { permission: "MANAGE_USERS" },
      async () => NextResponse.json({ ok: true }),
    );

    const res = await callHandler(handler, createMockRequest({}));
    expect(res.status).toBe(403);

    const body = await res.json();
    expect(body.error).toBe("Forbidden");
  });

  it("proceeds when user has the required permission", async () => {
    mockGetCurrentUser.mockResolvedValue(mockSessionUser({ permissions: ["MANAGE_USERS"] }));

    const handler = withHandler(
      { permission: "MANAGE_USERS" },
      async () => NextResponse.json({ ok: true }),
    );

    const res = await callHandler(handler, createMockRequest({}));
    expect(res.status).toBe(200);
  });

  it("does not check permissions when no permission config", async () => {
    mockGetCurrentUser.mockResolvedValue(mockSessionUser({ permissions: [] }));

    const handler = withHandler(
      {},
      async () => NextResponse.json({ ok: true }),
    );

    const res = await callHandler(handler, createMockRequest({}));
    expect(res.status).toBe(200);
  });
});

// ─── Project Access ───────────────────────────────────────────────

describe("withHandler — project access", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockCheckRateLimit.mockReturnValue(true);
  });

  it("returns 400 when projectAccess is true but no project ID in params", async () => {
    mockGetCurrentUser.mockResolvedValue(mockSessionUser({ permissions: [] }));

    const handler = withHandler(
      { projectAccess: true },
      async () => NextResponse.json({ ok: true }),
    );

    const res = await callHandler(handler, createMockRequest({}), {});
    expect(res.status).toBe(400);

    const body = await res.json();
    expect(body.error).toContain("Project ID required");
  });

  it("returns 403 when user cannot access the project", async () => {
    mockGetCurrentUser.mockResolvedValue(mockSessionUser({ permissions: [] }));
    mockCanViewProject.mockResolvedValue(false);

    const handler = withHandler(
      { projectAccess: true },
      async () => NextResponse.json({ ok: true }),
    );

    const res = await callHandler(handler, createMockRequest({}), { id: "proj-1" });
    expect(res.status).toBe(403);
  });

  it("proceeds when user has ADMIN global role", async () => {
    mockGetCurrentUser.mockResolvedValue(mockSessionUser({ globalRole: "ADMIN" }));
    mockCanViewProject.mockResolvedValue(true);
    mockCanEditProject.mockResolvedValue(true);

    const handler = withHandler(
      { projectAccess: true },
      async () => NextResponse.json({ ok: true }),
    );

    const res = await callHandler(handler, createMockRequest({}), { id: "proj-1" });
    expect(res.status).toBe(200);
  });

  it("uses custom projectIdParam when specified", async () => {
    mockGetCurrentUser.mockResolvedValue(mockSessionUser({ globalRole: "ADMIN" }));
    mockCanViewProject.mockResolvedValue(true);
    mockCanEditProject.mockResolvedValue(true);

    const handler = withHandler(
      { projectAccess: true, projectIdParam: "projectId" },
      async () => NextResponse.json({ ok: true }),
    );

    // No "id" param, but "projectId" is present
    const res = await callHandler(handler, createMockRequest({}), {
      projectId: "proj-1",
    });
    expect(res.status).toBe(200);
  });
});

// ─── Body Validation ──────────────────────────────────────────────

const testSchema = z.object({
  name: z.string().min(1),
  value: z.number(),
});

describe("withHandler — body validation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockCheckRateLimit.mockReturnValue(true);
    mockGetCurrentUser.mockResolvedValue(mockSessionUser());
  });

  it("returns 400 on invalid JSON body", async () => {
    const handler = withHandler(
      { schema: testSchema },
      async () => NextResponse.json({ ok: true }),
    );

    // Create a POST request with invalid JSON
    const req = new NextRequest(new URL("http://localhost/api/test"), {
      method: "POST",
      body: "not-json{{{",
      headers: { "content-type": "application/json", "x-forwarded-access-token": "mock-access-token" },
    });

    const res = await callHandler(handler, req);
    expect(res.status).toBe(400);

    const body = await res.json();
    expect(body.error).toBe("Invalid JSON body");
  });

  it("returns 400 with validation issues when body fails schema", async () => {
    const handler = withHandler(
      { schema: testSchema },
      async () => NextResponse.json({ ok: true }),
    );

    const req = createMockRequest({
      method: "POST",
      body: { name: "", value: "not-a-number" },
    });

    const res = await callHandler(handler, req);
    expect(res.status).toBe(400);

    const body = await res.json();
    expect(body.error).toBe("Validation failed");
    expect(body.issues).toBeDefined();
    expect(Array.isArray(body.issues)).toBe(true);
  });

  it("passes validated body to handler", async () => {
    let capturedBody: unknown;

    const handler = withHandler(
      { schema: testSchema },
      async (ctx) => {
        capturedBody = ctx.body;
        return NextResponse.json({ ok: true });
      },
    );

    const req = createMockRequest({
      method: "POST",
      body: { name: "test", value: 42 },
    });

    const res = await callHandler(handler, req);
    expect(res.status).toBe(200);
    expect(capturedBody).toEqual({ name: "test", value: 42 });
  });

  it("skips body validation for GET requests", async () => {
    let wasCalled = false;

    const handler = withHandler(
      { schema: testSchema },
      async () => {
        wasCalled = true;
        return NextResponse.json({ ok: true });
      },
    );

    const req = createMockRequest({ method: "GET" });
    const res = await callHandler(handler, req);

    expect(res.status).toBe(200);
    expect(wasCalled).toBe(true);
  });

  it("skips body validation for DELETE requests", async () => {
    const handler = withHandler(
      { schema: testSchema },
      async () => NextResponse.json({ ok: true }),
    );

    const req = createMockRequest({ method: "DELETE" });
    const res = await callHandler(handler, req);
    expect(res.status).toBe(200);
  });
});

// ─── Error Handling ───────────────────────────────────────────────
// Databricks SQL has no P2002/P2025-style error codes — src/lib/db/* throws
// typed ConflictError/NotFoundError instead, mapped here by `instanceof`.

describe("withHandler — error handling", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockCheckRateLimit.mockReturnValue(true);
    mockGetCurrentUser.mockResolvedValue(mockSessionUser());
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns 409 for ConflictError (unique constraint)", async () => {
    const handler = withHandler({}, async () => {
      throw new ConflictError("A record with this value already exists");
    });

    const res = await callHandler(handler, createMockRequest({}));
    expect(res.status).toBe(409);

    const body = await res.json();
    expect(body.error).toContain("already exists");
  });

  it("returns 404 for NotFoundError", async () => {
    const handler = withHandler({}, async () => {
      throw new NotFoundError();
    });

    const res = await callHandler(handler, createMockRequest({}));
    expect(res.status).toBe(404);

    const body = await res.json();
    expect(body.error).toContain("not found");
  });

  it("returns 500 with generic message for unknown errors", async () => {
    const handler = withHandler({}, async () => {
      throw new Error("Sensitive internal error details");
    });

    const res = await callHandler(handler, createMockRequest({}));
    expect(res.status).toBe(500);

    const body = await res.json();
    expect(body.error).toBe("Internal server error");
    // Must NOT leak internal error details
    expect(JSON.stringify(body)).not.toContain("Sensitive");
  });
});

// ─── Integration: Full Pipeline ───────────────────────────────────

describe("withHandler — integration", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockCheckRateLimit.mockReturnValue(true);
    mockGetCurrentUser.mockResolvedValue(
      mockSessionUser({ id: "user-42", permissions: ["MANAGE_USERS"] }),
    );
  });

  it("passes correct context to the handler", async () => {
    let capturedCtx: any;
    const bodySchema = z.object({ title: z.string() });

    const handler = withHandler(
      {
        permission: "MANAGE_USERS",
        rateLimit: { key: "test", limit: 100, windowMs: 60_000 },
        schema: bodySchema,
      },
      async (ctx) => {
        capturedCtx = ctx;
        return NextResponse.json({ ok: true });
      },
    );

    const req = createMockRequest({
      method: "POST",
      body: { title: "My Project" },
    });

    const res = await callHandler(handler, req, { id: "proj-1" });

    expect(res.status).toBe(200);
    expect(capturedCtx.user.id).toBe("user-42");
    expect(capturedCtx.user.permissions).toContain("MANAGE_USERS");
    expect(capturedCtx.user.globalRole).toBe("MEMBER");
    expect(capturedCtx.params).toEqual({ id: "proj-1" });
    expect(capturedCtx.body).toEqual({ title: "My Project" });
    // No `prisma` field anymore — routes import from src/lib/db/* directly.
    expect(capturedCtx.prisma).toBeUndefined();
  });
});
