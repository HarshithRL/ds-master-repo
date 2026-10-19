import { NextRequest, NextResponse } from "next/server";
import type { ZodType, ZodError } from "zod";
import { getCurrentUserFromRequest, type SessionUser } from "./current-user";
import {
  sessionHasPermission,
  hasPortfolioEdit,
  whyAdminOnly,
  whyPermissionDenied,
  type Permission,
} from "./permissions";
import {
  canViewProject,
  canEditProject,
  whyCantEditProject,
  whyCantViewProject,
} from "./access-control";
import { ConflictError, NotFoundError } from "./db/errors";
import { checkRateLimit, type RateLimitConfig } from "./rate-limit";
import { extractIp } from "./security-audit";
import { withAccessToken } from "./request-context";
import { closeRequestDatabricksClient } from "./databricks-sql";

// Re-export for convenience — route files only need to import from api-handler
export { createAuditLog, diffObjects } from "./audit";

// ─── Types ────────────────────────────────────────────────────────

export type HandlerContext<
  TBody = undefined,
  TParams extends Record<string, string> = Record<string, string>,
> = {
  req: NextRequest;
  user: SessionUser;
  params: TParams;
  body: TBody;
};

type HandlerConfig<TBody = undefined> = {
  /** Require authentication (default: true) */
  auth?: boolean;
  /** Require a specific admin-module permission */
  permission?: Permission;
  /** Require ADMIN globalRole (strict — admins-only routes like snapshots) */
  requireAdmin?: boolean;
  /**
   * Project-level access check using params[projectIdParam].
   * Method-aware by default:
   *   - GET    → canViewProject (executives, sponsors, owners, scope grants OK)
   *   - others → canEditProject (admin or ProjectAssignment PM/PMO only)
   * Set to "edit" to force edit-level even on GET.
   */
  projectAccess?: boolean | "edit";
  /** Param key for the project ID (default: "id") */
  projectIdParam?: string;
  /** Zod schema for request body validation (POST/PUT/PATCH) */
  schema?: ZodType<TBody>;
  /** Rate limiting config */
  rateLimit?: RateLimitConfig;
};

type BusinessLogic<TBody, TParams extends Record<string, string>> = (
  ctx: HandlerContext<TBody, TParams>,
) => Promise<NextResponse>;

type NextRouteHandler<TParams extends Record<string, string>> = (
  req: NextRequest,
  context: { params: Promise<TParams> },
) => Promise<NextResponse>;

// ─── Partial-update helper ────────────────────────────────────────

/**
 * Copy each *defined* field from `body` into `target` for the listed keys.
 * Skips keys whose body value is `undefined`; **preserves explicit `null`**
 * so callers can clear nullable fields. Returns the mutated target.
 *
 * Use this anywhere a route does the repetitive pattern:
 *   if (body.x !== undefined) updateData.x = body.x;
 *   if (body.y !== undefined) updateData.y = body.y;
 *   ...
 *
 * For fields that need transformation (Date parsing, connect/disconnect,
 * sanitization) handle those separately before/after the call.
 */
export function applyPartial<TBody extends Record<string, unknown>>(
  target: Record<string, unknown>,
  body: TBody,
  keys: readonly (keyof TBody & string)[],
): Record<string, unknown> {
  for (const key of keys) {
    const value = body[key];
    if (value !== undefined) target[key] = value;
  }
  return target;
}

// ─── Zod error formatting ─────────────────────────────────────────

function formatZodError(error: ZodError): { path: string; message: string }[] {
  return error.issues.map((i) => ({
    path: i.path.join("."),
    message: i.message,
  }));
}

// ─── The main HOF ─────────────────────────────────────────────────

export function withHandler<
  TBody = undefined,
  TParams extends Record<string, string> = Record<string, string>,
>(
  config: HandlerConfig<TBody>,
  handler: BusinessLogic<TBody, TParams>,
): NextRouteHandler<TParams> {
  return async (req, context) => {
    // Every Databricks connection this request makes uses the caller's own
    // forwarded, downscoped access token (user authorization — see
    // src/lib/request-context.ts) instead of the app's service principal.
    // No token, no DB access at all — reject up front rather than letting
    // every downstream src/lib/db/* call fail one by one.
    const accessToken = req.headers.get("x-forwarded-access-token");
    if (!accessToken) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    return withAccessToken(accessToken, () => handleRequest(req, context, config, handler));
  };
}

async function handleRequest<
  TBody,
  TParams extends Record<string, string>,
>(
  req: NextRequest,
  context: { params: Promise<TParams> },
  config: HandlerConfig<TBody>,
  handler: BusinessLogic<TBody, TParams>,
): Promise<NextResponse> {
    try {
      // 1. Rate limiting (before auth to protect the auth call)
      if (config.rateLimit) {
        const ip = extractIp(req.headers);
        if (!checkRateLimit(config.rateLimit, ip)) {
          return NextResponse.json(
            { error: "Too many requests. Please try again later." },
            { status: 429, headers: { "Retry-After": "60" } },
          );
        }
      }

      // 2. Auth check — identity comes from Databricks Apps' forwarded headers,
      // not a session cookie (see src/lib/current-user.ts).
      let user: SessionUser | undefined;
      if (config.auth !== false) {
        const resolved = await getCurrentUserFromRequest(req);
        if (!resolved) {
          return NextResponse.json(
            { error: "Unauthorized" },
            { status: 401 },
          );
        }
        user = resolved;
      }

      // 3. Permission check (admin module flag)
      if (config.permission && user) {
        if (!sessionHasPermission(user, config.permission)) {
          return NextResponse.json(
            { error: "Forbidden", reason: whyPermissionDenied(user, config.permission) },
            { status: 403 },
          );
        }
      }

      // 3b. ADMIN-only check (snapshots, etc.)
      if (config.requireAdmin && user) {
        if (!hasPortfolioEdit(user)) {
          return NextResponse.json(
            { error: "Forbidden", reason: whyAdminOnly(user) },
            { status: 403 },
          );
        }
      }

      // 4. Resolve params
      const params = (await context.params) as TParams;

      // 5. Project access check — method-aware:
      //    GET → view-level (executives, sponsors, owners, scope grants OK)
      //    others (or projectAccess === "edit") → edit-level
      if (config.projectAccess && user) {
        const projectId = params[config.projectIdParam ?? "id"];
        if (!projectId) {
          return NextResponse.json(
            { error: "Project ID required" },
            { status: 400 },
          );
        }
        const isReadOp = req.method.toUpperCase() === "GET";
        const wantsEdit = config.projectAccess === "edit" || !isReadOp;
        const allowed = wantsEdit
          ? await canEditProject(user, projectId)
          : await canViewProject(user, projectId);
        if (!allowed) {
          const reason = wantsEdit
            ? await whyCantEditProject(user, projectId)
            : await whyCantViewProject(user, projectId);
          return NextResponse.json(
            { error: "Forbidden", reason },
            { status: 403 },
          );
        }
      }

      // 6. Body validation (only for methods with a body)
      let body = undefined as TBody;
      const method = req.method.toUpperCase();
      if (config.schema && ["POST", "PUT", "PATCH"].includes(method)) {
        let rawBody: unknown;
        try {
          rawBody = await req.json();
        } catch {
          return NextResponse.json(
            { error: "Invalid JSON body" },
            { status: 400 },
          );
        }
        const result = config.schema.safeParse(rawBody);
        if (!result.success) {
          return NextResponse.json(
            {
              error: "Validation failed",
              issues: formatZodError(result.error),
            },
            { status: 400 },
          );
        }
        body = result.data;
      }

      // 7. Business logic
      return await handler({
        req,
        user: user!,
        params,
        body,
      });
    } catch (error) {
      // Sanitized error response — never leak internals
      console.error(
        `[API Error] ${req.method} ${req.nextUrl.pathname}:`,
        error,
      );

      if (error instanceof ConflictError) {
        return NextResponse.json({ error: error.message }, { status: 409 });
      }
      if (error instanceof NotFoundError) {
        return NextResponse.json({ error: error.message }, { status: 404 });
      }

      return NextResponse.json(
        { error: "Internal server error" },
        { status: 500 },
      );
    } finally {
      await closeRequestDatabricksClient().catch(() => {});
    }
}
