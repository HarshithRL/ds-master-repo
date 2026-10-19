import { createAuditLogRow } from "./db/audit-logs";

export type SecurityEvent =
  | "LOGIN_SUCCESS"
  | "LOGIN_FAILED"
  | "LOGOUT"
  | "PERMISSION_CHANGED"
  | "USER_CREATED"
  | "USER_DEACTIVATED"
  | "USER_REACTIVATED"
  | "USER_DELETED";

interface SecurityEventParams {
  userId?: string;
  event: SecurityEvent;
  ipAddress?: string;
  userAgent?: string;
  reason?: string;
  metadata?: Record<string, unknown>;
}

/**
 * Log a security event to the audit_logs table.
 * Uses entity="Auth" for login/logout events and entity="Security" for user/permission events.
 * All metadata (IP, user agent, reason) stored in the `changes` JSON field.
 * Fire-and-forget — never blocks the calling flow.
 */
export function logSecurityEvent(params: SecurityEventParams): void {
  const entity = params.event.startsWith("LOGIN") || params.event === "LOGOUT"
    ? "Auth"
    : "Security";

  const changes: Record<string, { old: unknown; new: unknown }> = {};
  if (params.ipAddress) changes.ipAddress = { old: null, new: params.ipAddress };
  if (params.userAgent) changes.userAgent = { old: null, new: params.userAgent };
  if (params.reason) changes.reason = { old: null, new: params.reason };
  if (params.metadata) {
    for (const [k, v] of Object.entries(params.metadata)) changes[k] = { old: null, new: v };
  }

  createAuditLogRow({
    userId: params.userId ?? null,
    action: params.event,
    entity,
    changes: Object.keys(changes).length > 0 ? changes : null,
  }).catch((err) => console.error("[SecurityAudit] Failed to log event:", err));
}

/** Extract client IP from request headers. */
export function extractIp(headers: Headers): string {
  return (
    headers.get("x-forwarded-for")?.split(",")[0]?.trim() ||
    headers.get("x-real-ip") ||
    "unknown"
  );
}

/** Extract a truncated user agent string. */
export function extractUserAgent(headers: Headers): string {
  const ua = headers.get("user-agent") || "unknown";
  return ua.length > 200 ? ua.slice(0, 200) : ua;
}
