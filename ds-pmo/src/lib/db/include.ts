// Join emulation: Prisma's `include` fetched a primary row set plus its
// relations in one call; here that becomes one primary query + one batched
// query per relation (never per-row — same complexity class as what Prisma
// did under the hood), stitched back together in JS.

/** Attach a to-many relation: each parent gets an array of matching children. */
export function attachMany<P extends { id: string }, C, K extends string>(
  parents: P[],
  children: C[],
  childForeignKey: (child: C) => string | null | undefined,
  attachAs: K,
): (P & Record<K, C[]>)[] {
  const byParent = new Map<string, C[]>();
  for (const child of children) {
    const parentId = childForeignKey(child);
    if (!parentId) continue;
    const bucket = byParent.get(parentId);
    if (bucket) bucket.push(child);
    else byParent.set(parentId, [child]);
  }
  return parents.map((p) => ({ ...p, [attachAs]: byParent.get(p.id) ?? [] })) as (P & Record<K, C[]>)[];
}

/** Attach a to-one relation: each parent gets its single matching child (or null). */
export function attachOne<P, C extends { id: string }, K extends string>(
  parents: P[],
  children: C[],
  parentForeignKey: (parent: P) => string | null | undefined,
  attachAs: K,
): (P & Record<K, C | null>)[] {
  const byId = new Map(children.map((c) => [c.id, c]));
  return parents.map((p) => {
    const fk = parentForeignKey(p);
    return { ...p, [attachAs]: fk ? (byId.get(fk) ?? null) : null };
  }) as (P & Record<K, C | null>)[];
}
