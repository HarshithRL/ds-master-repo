import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

const mocks = vi.hoisted(() => ({
  getUserByEmail: vi.fn(),
  closeClient: vi.fn(),
  headers: vi.fn(),
}));

vi.mock("../db/users", () => ({ getUserByEmail: mocks.getUserByEmail }));
vi.mock("../databricks-sql", () => ({ closeRequestDatabricksClient: mocks.closeClient }));
vi.mock("next/headers", () => ({ headers: mocks.headers }));

import { getCurrentUserFromRequest, withCurrentUser } from "../current-user";
import { withAccessToken, getRequestStore } from "../request-context";

const user = { id: "reader", email: "reader@etexgroup.com", name: "Reader", image: null,
  globalRole: "MEMBER", permissions: [], isActive: true };

function request(email = user.email) {
  return new NextRequest("https://pmo.example/api/users", { headers: { "x-forwarded-email": email } });
}

beforeEach(() => {
  vi.resetAllMocks();
  mocks.getUserByEmail.mockResolvedValue({ ...user });
  mocks.closeClient.mockResolvedValue(undefined);
});

describe("PMO user authorization", () => {
  it("does not provision unknown users", async () => {
    mocks.getUserByEmail.mockResolvedValue(null);
    expect(await withAccessToken("token", () => getCurrentUserFromRequest(request()))).toBeNull();
  });

  it("rejects missing or external identities before SQL", async () => {
    for (const email of ["", "other@example.com", "reader@etexgroup.com.attacker.test"]) {
      expect(await getCurrentUserFromRequest(request(email))).toBeNull();
    }
    expect(mocks.getUserByEmail).not.toHaveBeenCalled();
  });

  it("observes deactivation and demotion on the next request without cached privileges", async () => {
    mocks.getUserByEmail.mockResolvedValueOnce({ ...user, globalRole: "ADMIN" })
      .mockResolvedValueOnce({ ...user, globalRole: "MEMBER" })
      .mockResolvedValueOnce({ ...user, isActive: false });
    expect((await getCurrentUserFromRequest(request()))?.globalRole).toBe("ADMIN");
    expect((await getCurrentUserFromRequest(request()))?.globalRole).toBe("MEMBER");
    expect(await getCurrentUserFromRequest(request())).toBeNull();
    expect(mocks.getUserByEmail).toHaveBeenCalledTimes(3);
  });

  it("resolves a reader without database writes and closes the server-component client", async () => {
    mocks.headers.mockResolvedValue(new Headers({ "x-forwarded-email": user.email, "x-forwarded-access-token": "reader-token" }));
    const result = await withCurrentUser(async (resolved) => {
      expect(getRequestStore().accessToken).toBe("reader-token");
      return resolved;
    });
    expect(result?.id).toBe(user.id);
    expect(mocks.closeClient).toHaveBeenCalledOnce();
  });

  it("closes the client when server rendering fails", async () => {
    mocks.headers.mockResolvedValue(new Headers({ "x-forwarded-email": user.email, "x-forwarded-access-token": "reader-token" }));
    await expect(withCurrentUser(async () => { throw new Error("render failed"); })).rejects.toThrow("render failed");
    expect(mocks.closeClient).toHaveBeenCalledOnce();
  });

  it("rejects a missing delegated token without accessing SQL", async () => {
    mocks.headers.mockResolvedValue(new Headers({ "x-forwarded-email": user.email }));
    expect(await withCurrentUser(async (resolved) => resolved)).toBeNull();
    expect(mocks.getUserByEmail).not.toHaveBeenCalled();
  });
});