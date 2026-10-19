// ─── In-memory sliding window rate limiter ────────────────────────
// Map-based, zero dependencies. Replace with Redis for multi-instance.

export type RateLimitConfig = {
  /** Bucket identifier (e.g., "mutation", "auth") */
  key: string;
  /** Max requests allowed per window */
  limit: number;
  /** Window size in milliseconds */
  windowMs: number;
};

export const RATE_LIMITS = {
  /** Read endpoints: 100 req/min */
  read: { key: "read", limit: 100, windowMs: 60_000 },
  /** Mutation endpoints: 30 req/min */
  mutation: { key: "mutation", limit: 30, windowMs: 60_000 },
  /** Auth-sensitive: 20 req/min (a single login flow uses 2-3 requests) */
  auth: { key: "auth", limit: 20, windowMs: 60_000 },
  /** File upload: 10 req/min */
  upload: { key: "upload", limit: 10, windowMs: 60_000 },
} as const satisfies Record<string, RateLimitConfig>;

// Map<compositeKey, timestamps[]>
const store = new Map<string, number[]>();

const CLEANUP_INTERVAL = 5 * 60_000;
let lastCleanup = Date.now();

function cleanup(now: number): void {
  if (now - lastCleanup < CLEANUP_INTERVAL) return;
  lastCleanup = now;
  const maxWindow = 5 * 60_000;
  for (const [key, timestamps] of store) {
    const valid = timestamps.filter((t) => t > now - maxWindow);
    if (valid.length === 0) store.delete(key);
    else store.set(key, valid);
  }
}

/**
 * Returns `true` if the request is allowed, `false` if rate-limited.
 */
export function checkRateLimit(
  config: RateLimitConfig,
  identifier: string,
): boolean {
  const now = Date.now();
  cleanup(now);

  const compositeKey = `${config.key}:${identifier}`;
  const timestamps = store.get(compositeKey) ?? [];
  const valid = timestamps.filter((t) => t > now - config.windowMs);

  if (valid.length >= config.limit) {
    store.set(compositeKey, valid);
    return false;
  }

  valid.push(now);
  store.set(compositeKey, valid);
  return true;
}
