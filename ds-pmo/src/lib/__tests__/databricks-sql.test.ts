import { beforeEach, expect, it, vi } from "vitest";
const mocks = vi.hoisted(() => ({
  finished: vi.fn(), closeOperation: vi.fn(), closeSession: vi.fn(), connect: vi.fn(), execute: vi.fn(),
}));
vi.mock("@databricks/sql", () => ({
  DBSQLClient: class {
    connect = mocks.connect;
    async openSession() { return { executeStatement: mocks.execute, close: mocks.closeSession }; }
  },
}));
vi.mock("../db/connection-config", () => ({ resolveConnectionConfig: () => ({ host: "dev.example", path: "/sql/1.0/warehouses/dev" }) }));
import { runDatabricksExecute } from "../databricks-sql";
import { withAccessToken } from "../request-context";

beforeEach(() => {
  vi.resetAllMocks();
  mocks.connect.mockResolvedValue(undefined);
  mocks.execute.mockResolvedValue({ finished: mocks.finished, close: mocks.closeOperation });
  mocks.finished.mockResolvedValue(undefined);
});

it("waits for asynchronous DML to finish before closing and returning success", async () => {
  let complete!: () => void;
  const pending = new Promise<void>((resolve) => { complete = resolve; });
  mocks.finished.mockReturnValue(pending);
  const write = withAccessToken("delegated-token", () => runDatabricksExecute("UPDATE PMO_users SET name = ?", ["Updated"]));
  await vi.waitFor(() => expect(mocks.finished).toHaveBeenCalledOnce());
  expect(mocks.closeOperation).not.toHaveBeenCalled();
  complete();
  await write;
  expect(mocks.connect).toHaveBeenCalledWith(expect.objectContaining({ token: "delegated-token", authType: "access-token" }));
  expect(mocks.execute).toHaveBeenCalledWith("UPDATE PMO_users SET name = ?", { runAsync: true, ordinalParameters: ["Updated"] });
  expect(mocks.closeOperation).toHaveBeenCalledOnce();
  expect(mocks.closeSession).toHaveBeenCalledOnce();
});

it("propagates server-side write errors and still closes both operation and session", async () => {
  mocks.finished.mockRejectedValue(new Error("MODIFY denied"));
  await expect(withAccessToken("delegated-token", () => runDatabricksExecute("DELETE FROM PMO_projects"))).rejects.toThrow("MODIFY denied");
  expect(mocks.closeOperation).toHaveBeenCalledOnce();
  expect(mocks.closeSession).toHaveBeenCalledOnce();
});

it("refuses SQL execution without a request-scoped user token", async () => {
  await expect(runDatabricksExecute("DELETE FROM PMO_projects")).rejects.toThrow("No Databricks request context");
  expect(mocks.connect).not.toHaveBeenCalled();
});