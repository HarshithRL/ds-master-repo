import type { NextRequest } from "next/server";
import { getUserByEmail } from "./db/users";
import type { GlobalRole } from "./db/models";
import { withAccessToken } from "./request-context";
import { closeRequestDatabricksClient } from "./databricks-sql";

// Identity resolver replacing NextAuth. There is no login UI, no session
// cookie, no JWT — Databricks Apps' own reverse proxy authenticates the user
// against the workspace *before* the request ever reaches this app, and
// forwards their identity via the `x-forwarded-email` header, plus (with
// user authorization enabled) a downscoped `x-forwarded-access-token` used
// for every Databricks SQL connection this request makes — see
// https://docs.databricks.com/aws/en/dev-tools/databricks-apps/auth and
// src/lib/request-context.ts. This module trusts those headers
// unconditionally — that's a hard security dependency on running
// exclusively behind the Databricks Apps proxy; it must never be exposed
// any other way (e.g. a raw port, a different proxy).

export type SessionUser = {
  id: string;
  name?: string | null;
  email?: string | null;
  image?: string | null;
  globalRole: GlobalRole;
  permissions: string[];
};

function toSessionUser(row: Awaited<ReturnType<typeof getUserByEmail>>): SessionUser | null {
  if (!row) return null;
  return {
    id: row.id,
    name: row.name,
    email: row.email,
    image: row.image,
    globalRole: row.globalRole,
    permissions: row.permissions,
  };
}

/** Must be called from inside an active withAccessToken() scope (see below). */
async function resolveFromHeaders(headers: Headers): Promise<SessionUser | null> {
  const email = headers.get("x-forwarded-email")?.toLowerCase().trim();
  if (!email || !/^[^@\s]+@etexgroup\.com$/.test(email)) return null;
  const row = await getUserByEmail(email);
  if (!row?.isActive) return null;
  return toSessionUser(row);
}

/**
 * For Server Components / layouts. Every Databricks connection this request
 * makes uses the caller's own forwarded access token (user authorization —
 * see request-context.ts), so this establishes that context for the whole
 * callback, not just the identity lookup. Any further DB access the page
 * needs (e.g. fetchProfileData) must happen INSIDE `fn`, not after this
 * returns — the token context ends when `fn`'s promise settles.
 */
export async function withCurrentUser<T>(fn: (user: SessionUser | null) => Promise<T>): Promise<T> {
  const { headers } = await import("next/headers");
  const h = await headers();
  const token = h.get("x-forwarded-access-token");
  if (!token) return fn(null);
  return withAccessToken(token, async () => {
    try {
      return await fn(await resolveFromHeaders(h));
    } finally {
      await closeRequestDatabricksClient();
    }
  });
}

/**
 * For API route handlers — withHandler already establishes the
 * withAccessToken() context around the whole request before calling this.
 */
export async function getCurrentUserFromRequest(req: NextRequest): Promise<SessionUser | null> {
  return resolveFromHeaders(req.headers);
}
