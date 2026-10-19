import { NextRequest } from "next/server";

export function createMockRequest(options: {
  method?: string;
  headers?: Record<string, string>;
  body?: unknown;
  url?: string;
}): NextRequest {
  const {
    method = "GET",
    headers = {},
    body,
    url = "http://localhost/api/test",
  } = options;

  // withHandler rejects any request with no forwarded Databricks access
  // token (user-authorization mode) before auth/business logic ever runs —
  // default one in so tests aren't all forced to opt in individually.
  // Pass `{ headers: { "x-forwarded-access-token": "" } }` to simulate the
  // no-token case explicitly — withHandler treats an empty string the same
  // as a missing header (both are falsy).
  if (!("x-forwarded-access-token" in headers)) {
    headers["x-forwarded-access-token"] = "mock-access-token";
  }

  const init: Record<string, unknown> = { method, headers };
  if (body) {
    init.body = JSON.stringify(body);
    (headers as Record<string, string>)["content-type"] = "application/json";
  }
  return new NextRequest(new URL(url), init as any);
}

/** Matches src/lib/current-user.ts's `SessionUser` shape — what
 * getCurrentUserFromRequest resolves to (no more NextAuth session wrapper). */
export function mockSessionUser(overrides: {
  id?: string;
  email?: string;
  name?: string;
  permissions?: string[];
  globalRole?: "ADMIN" | "EXECUTIVE" | "MEMBER";
} = {}) {
  return {
    id: overrides.id ?? "user-1",
    email: overrides.email ?? "test@etexgroup.com",
    name: overrides.name ?? "Test User",
    permissions: overrides.permissions ?? [],
    globalRole: overrides.globalRole ?? "MEMBER",
  };
}
