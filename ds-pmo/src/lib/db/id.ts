/** Replaces Prisma's `cuid()` defaults — Delta tables generate no IDs themselves. */
export function newId(): string {
  return crypto.randomUUID();
}
