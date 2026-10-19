import { withHandler } from "@/lib/api-handler";
import { createUserSchema, type CreateUserInput } from "@/lib/validations";
import { RATE_LIMITS } from "@/lib/rate-limit";
import { NextResponse } from "next/server";
import { listUsers, getUserByEmail, createUser } from "@/lib/db/users";

// GET /api/users?search=...
// Returns users matching search query (name or email).
// Used by UserSelector — accessible to any authenticated user.
export const GET = withHandler(
  { rateLimit: RATE_LIMITS.read },
  async ({ req }) => {
    const { searchParams } = new URL(req.url);
    const search = searchParams.get("search") ?? "";

    const { users } = await listUsers({
      search: search || undefined,
      activeOnly: true,
      limit: 20,
    });

    const result = users.map((u) => ({
      id: u.id,
      name: u.name,
      email: u.email,
      emailVerified: u.emailVerified,
      image: u.image,
    }));

    return NextResponse.json(result);
  },
);

// POST /api/users
// Creates a user (name required, email optional).
// Name-only users are external stakeholders (sponsors, owners).
export const POST = withHandler<CreateUserInput>(
  { schema: createUserSchema, rateLimit: RATE_LIMITS.mutation },
  async ({ body }) => {
    if (body.email) {
      const existing = await getUserByEmail(body.email);
      if (existing) {
        return NextResponse.json(
          { error: "A user with this email already exists", user: existing },
          { status: 409 },
        );
      }
    }

    const created = await createUser({
      name: body.name.trim(),
      email: body.email?.trim() || null,
      globalRole: "MEMBER",
      permissions: [],
      isActive: true,
    });

    return NextResponse.json(
      {
        id: created.id,
        name: created.name,
        email: created.email,
        emailVerified: created.emailVerified,
        image: created.image,
      },
      { status: 201 },
    );
  },
);
