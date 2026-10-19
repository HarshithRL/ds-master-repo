import { selectRows, selectOne, insertRow, updateRow, deleteRows, countRows, findByIds } from "./query-builder";
import type { WhereCondition } from "./query-builder";
import { fromRow, toRow } from "./rowmap";
import { ConflictError } from "./errors";
import type { User, GlobalRole, Permission } from "./models";

const TABLE = "users";
const JSON_COLUMNS = ["permissions"];

function mapUser(row: Record<string, unknown>): User {
  const u = fromRow<Record<string, unknown>>(row, JSON_COLUMNS);
  // emailVerified has no column of its own — Prisma's NextAuth-era field is
  // synthesized from last_login_at (non-null = has been seen at least once),
  // keeping the API response shape byte-identical for existing consumers.
  return { ...u, emailVerified: u.lastLoginAt ?? null } as User;
}

export async function getUserById(id: string): Promise<User | null> {
  const row = await selectOne<Record<string, unknown>>(TABLE, { where: [{ type: "eq", column: "id", value: id }] });
  return row ? mapUser(row) : null;
}

export async function getUserByEmail(email: string): Promise<User | null> {
  const row = await selectOne<Record<string, unknown>>(TABLE, {
    where: [{ type: "eq", column: "email", value: email.toLowerCase() }],
  });
  return row ? mapUser(row) : null;
}

export async function getUsersByIds(ids: string[]): Promise<User[]> {
  const rows = await findByIds<Record<string, unknown>>(TABLE, "id", ids);
  return rows.map(mapUser);
}

export interface CreateUserInput {
  /** Name-only stakeholders (sponsors/owners with no login) omit email. */
  email?: string | null;
  name: string;
  image?: string | null;
  globalRole: GlobalRole;
  permissions: Permission[];
  isActive: boolean;
}

export async function createUser(input: CreateUserInput): Promise<User> {
  if (input.email) {
    const existing = await getUserByEmail(input.email);
    if (existing) throw new ConflictError("A user with this email already exists");
  }

  const now = new Date();
  const data = {
    email: input.email ? input.email.toLowerCase() : null,
    name: input.name,
    image: input.image ?? null,
    globalRole: input.globalRole,
    permissions: input.permissions,
    isActive: input.isActive,
    lastLoginAt: null as Date | null,
    createdAt: now,
    updatedAt: now,
  };
  const id = await insertRow(TABLE, toRow(data, JSON_COLUMNS));
  // Return the constructed object directly instead of reading back.
  // Delta Lake may not surface the row in a new session immediately
  // after INSERT (cross-session read-after-write visibility lag).
  return {
    id,
    ...data,
    emailVerified: null, // synthesized from lastLoginAt (see mapUser)
  } as User;
}

export async function updateUser(
  id: string,
  fields: Partial<Omit<CreateUserInput, "email">> & { email?: string },
): Promise<void> {
  await updateRow(id ? TABLE : TABLE, id, toRow({ ...fields, updatedAt: new Date() }, JSON_COLUMNS));
}

/** Fire-and-forget from the identity resolver — never blocks a request on failure. */
export async function updateLastLoginAt(id: string): Promise<void> {
  await updateRow(TABLE, id, toRow({ lastLoginAt: new Date() }));
}

export async function deleteUser(id: string): Promise<void> {
  await deleteRows(TABLE, [{ type: "eq", column: "id", value: id }]);
}

export interface ListUsersOptions {
  search?: string;
  /** Only active users — used by the public-ish user selector. */
  activeOnly?: boolean;
  limit?: number;
  offset?: number;
}

export async function listUsers(opts: ListUsersOptions = {}): Promise<{ users: User[]; total: number }> {
  const where: WhereCondition[] = [];
  if (opts.activeOnly) where.push({ type: "eq", column: "is_active", value: true });
  if (opts.search) {
    where.push({
      type: "or",
      conditions: [
        { type: "ilike", column: "name", value: opts.search },
        { type: "ilike", column: "email", value: opts.search },
      ],
    });
  }
  const [rows, total] = await Promise.all([
    selectRows<Record<string, unknown>>(TABLE, {
      where,
      orderBy: [{ column: "name", direction: "ASC" }],
      limit: opts.limit,
      offset: opts.offset,
    }),
    countRows(TABLE, where),
  ]);
  return { users: rows.map(mapUser), total };
}
