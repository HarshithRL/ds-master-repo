import {
  logSecurityEvent,
  extractIp,
  extractUserAgent,
  type SecurityEvent,
} from "../security-audit";

// ─── Mock the audit-log data-access function ───────────────────────
vi.mock("../db/audit-logs", () => ({
  createAuditLogRow: vi.fn().mockResolvedValue(undefined),
}));
import { createAuditLogRow } from "../db/audit-logs";

const mockCreate = createAuditLogRow as ReturnType<typeof vi.fn>;

// ─── extractIp ────────────────────────────────────────────────────

describe("extractIp", () => {
  it("returns first IP from x-forwarded-for", () => {
    const headers = new Headers({ "x-forwarded-for": "1.2.3.4, 5.6.7.8" });
    expect(extractIp(headers)).toBe("1.2.3.4");
  });

  it("trims whitespace from forwarded IP", () => {
    const headers = new Headers({ "x-forwarded-for": "  10.0.0.1 , 10.0.0.2" });
    expect(extractIp(headers)).toBe("10.0.0.1");
  });

  it("falls back to x-real-ip when x-forwarded-for is absent", () => {
    const headers = new Headers({ "x-real-ip": "192.168.1.1" });
    expect(extractIp(headers)).toBe("192.168.1.1");
  });

  it("returns 'unknown' when no IP headers are present", () => {
    const headers = new Headers();
    expect(extractIp(headers)).toBe("unknown");
  });

  it("prefers x-forwarded-for over x-real-ip", () => {
    const headers = new Headers({
      "x-forwarded-for": "1.1.1.1",
      "x-real-ip": "2.2.2.2",
    });
    expect(extractIp(headers)).toBe("1.1.1.1");
  });
});

// ─── extractUserAgent ─────────────────────────────────────────────

describe("extractUserAgent", () => {
  it("returns full user-agent when under 200 chars", () => {
    const headers = new Headers({ "user-agent": "Mozilla/5.0" });
    expect(extractUserAgent(headers)).toBe("Mozilla/5.0");
  });

  it("truncates user-agent to 200 characters when longer", () => {
    const longUA = "A".repeat(300);
    const headers = new Headers({ "user-agent": longUA });
    const result = extractUserAgent(headers);
    expect(result).toHaveLength(200);
    expect(result).toBe("A".repeat(200));
  });

  it("returns exactly 200 chars for a 200-char user-agent", () => {
    const exact = "B".repeat(200);
    const headers = new Headers({ "user-agent": exact });
    expect(extractUserAgent(headers)).toHaveLength(200);
  });

  it("returns 'unknown' when header is absent", () => {
    const headers = new Headers();
    expect(extractUserAgent(headers)).toBe("unknown");
  });
});

// ─── logSecurityEvent ─────────────────────────────────────────────

describe("logSecurityEvent", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockCreate.mockResolvedValue(undefined);
  });

  it('uses entity "Auth" for LOGIN_SUCCESS', () => {
    logSecurityEvent({ event: "LOGIN_SUCCESS" });
    expect(mockCreate).toHaveBeenCalledWith(
      expect.objectContaining({ entity: "Auth" }),
    );
  });

  it('uses entity "Auth" for LOGIN_FAILED', () => {
    logSecurityEvent({ event: "LOGIN_FAILED" });
    expect(mockCreate).toHaveBeenCalledWith(
      expect.objectContaining({ entity: "Auth" }),
    );
  });

  it('uses entity "Auth" for LOGOUT', () => {
    logSecurityEvent({ event: "LOGOUT" });
    expect(mockCreate).toHaveBeenCalledWith(
      expect.objectContaining({ entity: "Auth" }),
    );
  });

  const securityEvents: SecurityEvent[] = [
    "PERMISSION_CHANGED",
    "USER_CREATED",
    "USER_DEACTIVATED",
    "USER_REACTIVATED",
    "USER_DELETED",
  ];

  it.each(securityEvents)(
    'uses entity "Security" for %s',
    (event) => {
      logSecurityEvent({ event });
      expect(mockCreate).toHaveBeenCalledWith(
        expect.objectContaining({ entity: "Security" }),
      );
    },
  );

  it("includes ipAddress, userAgent, and reason in changes", () => {
    logSecurityEvent({
      event: "LOGIN_SUCCESS",
      ipAddress: "1.2.3.4",
      userAgent: "TestBrowser",
      reason: "email-otp",
    });

    expect(mockCreate).toHaveBeenCalledWith(
      expect.objectContaining({
        changes: expect.objectContaining({
          ipAddress: { old: null, new: "1.2.3.4" },
          userAgent: { old: null, new: "TestBrowser" },
          reason: { old: null, new: "email-otp" },
        }),
      }),
    );
  });

  it("merges metadata into changes", () => {
    logSecurityEvent({
      event: "LOGIN_FAILED",
      metadata: { email: "bad@example.com", provider: "resend" },
    });

    expect(mockCreate).toHaveBeenCalledWith(
      expect.objectContaining({
        changes: expect.objectContaining({
          email: { old: null, new: "bad@example.com" },
          provider: { old: null, new: "resend" },
        }),
      }),
    );
  });

  it("omits changes when no optional fields are provided", () => {
    logSecurityEvent({ event: "LOGOUT" });

    expect(mockCreate).toHaveBeenCalledWith(
      expect.objectContaining({ changes: null }),
    );
  });

  it("passes userId when provided", () => {
    logSecurityEvent({ event: "LOGIN_SUCCESS", userId: "user-1" });

    expect(mockCreate).toHaveBeenCalledWith(
      expect.objectContaining({ userId: "user-1" }),
    );
  });

  it("passes null userId when not provided", () => {
    logSecurityEvent({ event: "LOGIN_FAILED" });

    expect(mockCreate).toHaveBeenCalledWith(
      expect.objectContaining({ userId: null }),
    );
  });

  it("does not throw when the write rejects", () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    mockCreate.mockRejectedValueOnce(new Error("DB down"));

    // logSecurityEvent is fire-and-forget — should not throw
    expect(() => logSecurityEvent({ event: "LOGIN_SUCCESS" })).not.toThrow();

    consoleError.mockRestore();
  });
});
