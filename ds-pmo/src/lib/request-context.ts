import { AsyncLocalStorage } from "node:async_hooks";

// User-authorization mode: every Databricks SQL connection is made AS the
// end user (their forwarded, downscoped access token — see
// https://docs.databricks.com/aws/en/dev-tools/databricks-apps/auth), not
// the app's own service principal. That means the connection is inherently
// per-request, per-user — there is no single shared client anymore. This
// AsyncLocalStorage carries the current request's token (and its lazily-
// created Databricks client, cached by databricks-sql.ts) through the async
// call graph without threading a parameter through every src/lib/db/*
// function.

export interface RequestStore {
  accessToken: string;
  // Populated lazily by databricks-sql.ts; typed loosely here to avoid a
  // circular import between the two modules.
  databricksClient?: unknown;
}

const storage = new AsyncLocalStorage<RequestStore>();

export function withAccessToken<T>(accessToken: string, fn: () => Promise<T>): Promise<T> {
  return storage.run({ accessToken }, fn);
}

/** Throws if called outside a withAccessToken() scope — every DB call must run inside one. */
export function getRequestStore(): RequestStore {
  const store = storage.getStore();
  if (!store) {
    throw new Error(
      "No Databricks request context active — this code must run inside withAccessToken() " +
        "(set up per-request in withHandler / getCurrentUser).",
    );
  }
  return store;
}
