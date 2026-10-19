import { DBSQLClient } from "@databricks/sql";
import { getRequestStore } from "./request-context";
import { resolveConnectionConfig } from "./db/connection-config";

type DBSQLSession = Awaited<ReturnType<DBSQLClient["openSession"]>>;
export type DBSQLParameterValue = undefined | null | boolean | number | bigint | Date | string;

// The app's sole datastore: a Databricks SQL warehouse, queried on behalf of
// the signed-in user — every connection uses THEIR forwarded access token
// (see src/lib/request-context.ts), not the app's own service principal.
// Unity Catalog permissions are therefore enforced as the end user's own
// grants, not the app's — there is no app-level "CAN_USE the warehouse"
// shortcut anymore. Requires user_api_scopes: ["sql"] in databricks.yml.

async function createDatabricksClient(accessToken: string): Promise<DBSQLClient> {
  const { host, path } = resolveConnectionConfig();

  const client = new DBSQLClient();
  await client.connect({
    authType: "access-token",
    host,
    path,
    token: accessToken,
  });

  return client;
}

/**
 * One client per request, cached on that request's AsyncLocalStorage store
 * (not a module-level global — a global would leak one user's token/session
 * to every other concurrent request). Cheap to create since `access-token`
 * auth is just a stored token, no OAuth handshake like the old M2M flow.
 */
function getDatabricksClient(): Promise<DBSQLClient> {
  const store = getRequestStore();
  if (!store.databricksClient) {
    store.databricksClient = createDatabricksClient(store.accessToken);
  }
  return store.databricksClient as Promise<DBSQLClient>;
}

/** Close and forget this request's client. Call once, at the end of the request. */
export async function closeRequestDatabricksClient(): Promise<void> {
  const store = getRequestStore();
  const clientPromise = store.databricksClient as Promise<DBSQLClient> | undefined;
  if (!clientPromise) return;
  store.databricksClient = undefined;
  try {
    const client = await clientPromise;
    await client.close();
  } catch (err) {
    console.error("[databricks-sql] failed to close client:", err);
  }
}

async function withSession<T>(fn: (session: DBSQLSession) => Promise<T>): Promise<T> {
  const client = await getDatabricksClient();
  const session = await client.openSession();
  try {
    return await fn(session);
  } finally {
    await session.close();
  }
}

/**
 * Run a read query against the Databricks SQL warehouse and return all rows.
 * Opens a short-lived session on the shared client connection per call.
 * `parameters` are bound positionally (`?` placeholders in `statement`) to
 * avoid string-interpolating values (search terms, ids, ...) into SQL.
 */
export async function runDatabricksQuery<T = Record<string, unknown>>(
  statement: string,
  parameters?: DBSQLParameterValue[],
): Promise<T[]> {
  return withSession(async (session) => {
    const operation = await session.executeStatement(statement, {
      runAsync: true,
      ordinalParameters: parameters,
    });
    try {
      return (await operation.fetchAll()) as T[];
    } finally {
      await operation.close();
    }
  });
}

/**
 * Run a DDL/DML statement (CREATE TABLE, TRUNCATE, INSERT, ...) that doesn't
 * return rows. `parameters` are bound positionally (`?` placeholders in `statement`)
 * to avoid string-interpolating user-entered values into SQL.
 */
export async function runDatabricksExecute(
  statement: string,
  parameters?: DBSQLParameterValue[],
): Promise<void> {
  await withSession(async (session) => {
    const operation = await session.executeStatement(statement, {
      runAsync: true,
      ordinalParameters: parameters,
    });
    try {
      await operation.finished();
    } finally {
      await operation.close();
    }
  });
}
