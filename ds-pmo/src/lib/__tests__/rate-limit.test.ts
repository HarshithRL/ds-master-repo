import { RATE_LIMITS } from "../rate-limit";

// We need a fresh module for each test group to avoid shared state
function freshImport() {
  return import("../rate-limit") as Promise<typeof import("../rate-limit")>;
}

// ─── RATE_LIMITS constants ────────────────────────────────────────

describe("RATE_LIMITS", () => {
  it("defines read as 100 req/min", () => {
    expect(RATE_LIMITS.read).toEqual({
      key: "read",
      limit: 100,
      windowMs: 60_000,
    });
  });

  it("defines mutation as 30 req/min", () => {
    expect(RATE_LIMITS.mutation).toEqual({
      key: "mutation",
      limit: 30,
      windowMs: 60_000,
    });
  });

  it("defines auth as 20 req/min", () => {
    expect(RATE_LIMITS.auth).toEqual({
      key: "auth",
      limit: 20,
      windowMs: 60_000,
    });
  });

  it("defines upload as 10 req/min", () => {
    expect(RATE_LIMITS.upload).toEqual({
      key: "upload",
      limit: 10,
      windowMs: 60_000,
    });
  });
});

// ─── checkRateLimit ───────────────────────────────────────────────

describe("checkRateLimit", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    // Reset module state between tests
    vi.resetModules();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("allows a request when under the limit", async () => {
    const { checkRateLimit } = await freshImport();
    const config = { key: "test", limit: 5, windowMs: 60_000 };
    expect(checkRateLimit(config, "ip-1")).toBe(true);
  });

  it("allows exactly `limit` requests, then blocks", async () => {
    const { checkRateLimit } = await freshImport();
    const config = { key: "test", limit: 3, windowMs: 60_000 };

    expect(checkRateLimit(config, "ip-2")).toBe(true);
    expect(checkRateLimit(config, "ip-2")).toBe(true);
    expect(checkRateLimit(config, "ip-2")).toBe(true);
    // 4th should be blocked
    expect(checkRateLimit(config, "ip-2")).toBe(false);
  });

  it("tracks different identifiers independently", async () => {
    const { checkRateLimit } = await freshImport();
    const config = { key: "test", limit: 1, windowMs: 60_000 };

    expect(checkRateLimit(config, "ip-a")).toBe(true);
    expect(checkRateLimit(config, "ip-b")).toBe(true);
    // ip-a is now blocked, ip-b is too
    expect(checkRateLimit(config, "ip-a")).toBe(false);
    expect(checkRateLimit(config, "ip-b")).toBe(false);
  });

  it("tracks different config keys independently", async () => {
    const { checkRateLimit } = await freshImport();
    const readConfig = { key: "read", limit: 1, windowMs: 60_000 };
    const writeConfig = { key: "write", limit: 1, windowMs: 60_000 };

    expect(checkRateLimit(readConfig, "ip-x")).toBe(true);
    // Different key, same IP — should still be allowed
    expect(checkRateLimit(writeConfig, "ip-x")).toBe(true);
    // Same key — now blocked
    expect(checkRateLimit(readConfig, "ip-x")).toBe(false);
  });

  it("allows requests after the window expires", async () => {
    const { checkRateLimit } = await freshImport();
    const config = { key: "test", limit: 1, windowMs: 60_000 };

    expect(checkRateLimit(config, "ip-expire")).toBe(true);
    expect(checkRateLimit(config, "ip-expire")).toBe(false);

    // Advance past the window
    vi.advanceTimersByTime(60_001);

    expect(checkRateLimit(config, "ip-expire")).toBe(true);
  });

  it("implements sliding window correctly", async () => {
    const { checkRateLimit } = await freshImport();
    const config = { key: "test", limit: 2, windowMs: 60_000 };

    // T=0: first request
    expect(checkRateLimit(config, "ip-slide")).toBe(true);

    // T=30s: second request
    vi.advanceTimersByTime(30_000);
    expect(checkRateLimit(config, "ip-slide")).toBe(true);

    // T=30s: third request — blocked (2 within window)
    expect(checkRateLimit(config, "ip-slide")).toBe(false);

    // T=60.001s: first request expired, one slot opens
    vi.advanceTimersByTime(30_001);
    expect(checkRateLimit(config, "ip-slide")).toBe(true);
  });
});

// ─── cleanup ──────────────────────────────────────────────────────

describe("cleanup", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.resetModules();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("does not remove entries before 5-minute interval", async () => {
    const { checkRateLimit } = await freshImport();
    const config = { key: "test", limit: 2, windowMs: 60_000 };

    // Fill the limit
    checkRateLimit(config, "ip-cleanup");
    checkRateLimit(config, "ip-cleanup");

    // Advance 2 minutes (past window but before cleanup interval)
    vi.advanceTimersByTime(2 * 60_000);

    // Entry is stale but cleanup hasn't triggered the full purge cycle yet
    // However, checkRateLimit filters valid timestamps per-call, so the request
    // should succeed because the timestamps are older than windowMs
    expect(checkRateLimit(config, "ip-cleanup")).toBe(true);
  });

  it("removes expired entries after 5-minute cleanup interval", async () => {
    const { checkRateLimit } = await freshImport();
    const config = { key: "test", limit: 1, windowMs: 60_000 };

    checkRateLimit(config, "ip-gc");

    // Advance past cleanup interval (5 minutes)
    vi.advanceTimersByTime(5 * 60_000 + 1);

    // Trigger cleanup by calling checkRateLimit (cleanup runs at the start)
    // The old entry should be cleaned up and this should be allowed
    expect(checkRateLimit(config, "ip-gc")).toBe(true);
  });
});
