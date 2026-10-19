/* ═══════════════════════════════════════════════════════════════════
   Project calculations — single source of truth
   ───────────────────────────────────────────────────────────────────
   All numerical project math lives here:
     · Budget (BAC, ETC, EAC, VAC, CPI)
     · Schedule (buffer days, SPI, duration helpers)
     · Project-year derivations used by the budget breakdown grid
   Components, API routes, snapshots — anything that needs a derived
   number — imports from this file. No inline EVM math elsewhere.
   ═══════════════════════════════════════════════════════════════════ */

const MS_PER_DAY = 1000 * 60 * 60 * 24;

/* ── Budget ────────────────────────────────────────────────────── */

export type BudgetFields = {
  actuals: number;
  committed: number;
  expected: number;
  bac: number;
};

/** Actuals + Committed — cash already spoken for. */
export function calcActualsCommitted(b: Pick<BudgetFields, "actuals" | "committed">): number {
  return b.actuals + b.committed;
}

/** Estimate to Complete = Committed + Expected. */
export function calcETC(b: Pick<BudgetFields, "committed" | "expected">): number {
  return b.committed + b.expected;
}

/** Estimate at Completion = Actuals + Committed + Expected. */
export function calcEAC(b: Pick<BudgetFields, "actuals" | "committed" | "expected">): number {
  return b.actuals + b.committed + b.expected;
}

/** Variance at Completion = BAC − EAC (positive = under budget). */
export function calcVariance(b: BudgetFields): number {
  return b.bac - calcEAC(b);
}

/** Variance % of BAC (positive = under budget). */
export function calcVariancePct(b: BudgetFields): number {
  return b.bac !== 0 ? (calcVariance(b) / b.bac) * 100 : 0;
}

/** Sum a budget-breakdown line set into BAC. */
export function calcBAC(lines: { amount: number }[]): number {
  return lines.reduce((sum, l) => sum + l.amount, 0);
}

/**
 * Source-of-truth resolver for BAC.
 *
 * The persisted `budget.bac` column is denormalized — it should equal
 * Σ(BudgetLine.amount), but legacy / imported projects exist where only
 * a summary number was entered and no breakdown lines were ever created.
 *
 * Policy: when lines exist, lines win (Σ of lines is canonical).
 * When no lines exist, fall back to the stored value so legacy
 * imports keep their BAC until a PM enters a proper breakdown.
 */
export function resolveBac(
  budget: { bac: number },
  lines: { amount: number }[] | null | undefined,
): number {
  if (!lines || lines.length === 0) return budget.bac;
  return calcBAC(lines);
}

/**
 * API-boundary normalizer: returns the budget with `bac` overwritten by the
 * authoritative resolved value (Σ lines when present; cached value otherwise).
 * Use this once at every API endpoint that returns a budget so the rest of
 * the codebase can read `budget.bac` without worrying about cache drift.
 */
export function withResolvedBac<
  B extends { bac: number; lines?: { amount: number }[] | null },
>(budget: B): B {
  return { ...budget, bac: resolveBac(budget, budget.lines ?? null) };
}

/** Overspend = max(0, EAC − BAC). Shown on the inner ring when EAC > BAC. */
export function calcOverspend(b: BudgetFields): number {
  return Math.max(0, calcEAC(b) - b.bac);
}

/** Percentage of BAC a value represents. Returns 0 when BAC is non-positive. */
export function pctOfBac(value: number, bac: number): number {
  return bac > 0 ? (value / bac) * 100 : 0;
}

/**
 * Cost Performance proxy = BAC / EAC.
 * Returns null if BAC or EAC is non-positive (insufficient data).
 *
 * NB: This is a budget-headroom ratio, not canonical EVM CPI (= EV / AC).
 * It has the correct direction (>1 under budget, <1 over) and the same
 * fixed point at 1.0, so it slots into the CPI×SPI quadrant chart cleanly.
 */
export function calcCPI(b: BudgetFields | null | undefined): number | null {
  if (!b || b.bac <= 0) return null;
  const eac = calcEAC(b);
  if (eac <= 0) return null;
  return b.bac / eac;
}

/* ── Schedule ──────────────────────────────────────────────────── */

type DateInput = Date | string | null | undefined;

function toMs(d: DateInput): number | null {
  if (!d) return null;
  const t = new Date(d).getTime();
  return Number.isFinite(t) ? t : null;
}

/**
 * Schedule buffer in days = planned − expected.
 * Positive = ahead of plan, negative = slipping.
 * Always derived live — there is no stored column.
 */
export function calcScheduleBufferDays(planned: DateInput, expected: DateInput): number | null {
  const p = toMs(planned);
  const e = toMs(expected);
  if (p === null || e === null) return null;
  return Math.round((p - e) / MS_PER_DAY);
}

/**
 * Planned duration in calendar days (Math.ceil), 0 when either bound is missing
 * or the range is non-positive. Used by exposure calcs that compare a delay
 * (in days) against the full planned span.
 */
export function calcPlannedDuration(start: DateInput, end: DateInput): number {
  const s = toMs(start);
  const e = toMs(end);
  if (s === null || e === null) return 0;
  const diff = e - s;
  return diff > 0 ? Math.ceil(diff / MS_PER_DAY) : 0;
}

/**
 * Resolves the effective start of a project — the user-entered actual
 * start date if available, otherwise the row creation timestamp.
 * Returned as a Date (or null when both are missing).
 */
export function getProjectStartDate(p: {
  actualStartDate: DateInput;
  createdAt: DateInput;
}): Date | null {
  const ms = toMs(p.actualStartDate) ?? toMs(p.createdAt);
  return ms === null ? null : new Date(ms);
}

/**
 * Schedule Performance Index using actual start date as the baseline.
 *   SPI = (plannedEnd − actualStart) / (expectedEnd − actualStart)
 *
 * Direction: >1 = ahead of schedule, <1 = behind. Returns null when any
 * required date is missing or the expected duration is non-positive.
 *
 * NB: Not canonical EVM SPI (= EV / PV). It's a duration ratio anchored
 * to a real start date, which is what this codebase actually tracks.
 */
export function calcSPI(p: {
  actualStartDate: DateInput;
  plannedCompletionDate: DateInput;
  expectedCompletionDate: DateInput;
}): number | null {
  const start = toMs(p.actualStartDate);
  const planned = toMs(p.plannedCompletionDate);
  const expected = toMs(p.expectedCompletionDate);
  if (start === null || planned === null || expected === null) return null;
  const plannedDuration = planned - start;
  const expectedDuration = expected - start;
  if (expectedDuration <= 0 || plannedDuration <= 0) return null;
  return plannedDuration / expectedDuration;
}

/* ── Project years (for budget breakdown grid) ─────────────────── */

function yearOf(d: DateInput): number | null {
  const ms = toMs(d);
  return ms === null ? null : new Date(ms).getFullYear();
}

/**
 * Inclusive list of years covered by a project, ordered ascending.
 *   start year = actualStartDate year, falling back to createdAt year
 *                if the project hasn't recorded a real start yet.
 *   end year   = max(plannedEnd, expectedEnd) year. Falls back to
 *                +4 years from start if neither end date is set.
 *
 * Both ends are clamped so a misordered project always shows at least one row.
 */
export function deriveProjectYears(p: {
  actualStartDate: DateInput;
  plannedCompletionDate: DateInput;
  expectedCompletionDate: DateInput;
  createdAt: DateInput;
}): number[] {
  const startYear = yearOf(p.actualStartDate) ?? yearOf(p.createdAt);
  if (startYear === null) return [];

  const plannedY = yearOf(p.plannedCompletionDate);
  const expectedY = yearOf(p.expectedCompletionDate);
  let endYear: number;
  if (plannedY !== null && expectedY !== null) endYear = Math.max(plannedY, expectedY);
  else if (plannedY !== null) endYear = plannedY;
  else if (expectedY !== null) endYear = expectedY;
  else endYear = startYear + 4;

  const last = Math.max(endYear, startYear);
  const years: number[] = [];
  for (let y = startYear; y <= last; y++) years.push(y);
  return years;
}
