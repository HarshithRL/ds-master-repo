import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Pick a readable text color (white or near-black) for a given background hex.
 * Used by colored bands/chips so labels stay legible across the palette.
 */
export function contrastText(hex: string): string {
  const c = hex.replace("#", "");
  const r = parseInt(c.substring(0, 2), 16);
  const g = parseInt(c.substring(2, 4), 16);
  const b = parseInt(c.substring(4, 6), 16);
  const lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return lum > 0.6 ? "#1A1A2E" : "#FFFFFF";
}

/** Round to N decimal places, eliminating floating-point noise. */
export function roundTo(value: number, decimals: number = 0): number {
  const factor = 10 ** decimals;
  return Math.round(value * factor) / factor;
}

/**
 * Format a number with period (.) as thousands separator.
 * All budget/KPI displays use this for consistency.
 *
 * Examples: 1234 → "1.234", 3.4 with decimals=1 → "3,4"
 */
export function formatAmount(value: number, decimals: number = 0): string {
  return Math.abs(value).toLocaleString("de-DE", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/**
 * Format a number as budget currency.
 * - Period as thousands separator, no decimals
 * - Default suffix "k€"
 * - Handles null/undefined → "—"
 * - `signed: true` prepends +/- for variance display
 * - `compact: true` converts ≥1 000 → "1.2M€" style
 */
export function formatCurrency(
  value: number | null | undefined,
  {
    suffix = " k€",
    signed = false,
    compact = false,
    decimals = 1,
  }: { suffix?: string; signed?: boolean; compact?: boolean; decimals?: number } = {},
): string {
  if (value == null) return "—";

  // Round first so tiny values that snap to 0 render cleanly (no "−0,0").
  const rounded = roundTo(value, decimals);
  if (rounded === 0) return `${signed ? "+" : ""}0${suffix}`;

  const sign = signed ? (rounded > 0 ? "+" : "−") : rounded < 0 ? "−" : "";

  if (compact && Math.abs(rounded) >= 1_000) {
    return `${sign}${(Math.abs(rounded) / 1_000).toFixed(1)}M€`;
  }

  const formatted = formatAmount(rounded, decimals);
  return `${sign}${formatted}${suffix}`;
}

/**
 * Format a variance/delta where positive = good (under budget, ahead of schedule).
 * Rounds first so tiny negatives (e.g. -0.04) don't render as "−0,0"; anything
 * that rounds to 0 is "+0" with positive sentiment. Use the returned sentiment
 * to color the value consistently (green/red/muted).
 */
export function formatVariance(
  value: number | null | undefined,
  {
    decimals = 1,
    suffix = " k€",
  }: { decimals?: number; suffix?: string } = {},
): { display: string; sentiment: "positive" | "negative" | "neutral" } {
  if (value == null) return { display: "—", sentiment: "neutral" };

  const rounded = roundTo(value, decimals);
  if (rounded === 0) return { display: `+0${suffix}`, sentiment: "positive" };

  const sign = rounded > 0 ? "+" : "−";
  return {
    display: `${sign}${formatAmount(rounded, decimals)}${suffix}`,
    sentiment: rounded > 0 ? "positive" : "negative",
  };
}

export function formatDate(date: Date | string | null | undefined): string {
  if (!date) return "—";
  const d = typeof date === "string" ? new Date(date) : date;
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

/** Format as dd/mm/yy — compact date for table columns. */
export function formatDateShort(date: Date | string | null | undefined): string {
  if (!date) return "—";
  const d = typeof date === "string" ? new Date(date) : date;
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const yy = String(d.getFullYear()).slice(-2);
  return `${dd}/${mm}/${yy}`;
}

export function formatPercent(value: number): string {
  return `${Math.round(value)}%`;
}

/** Full date + time, en-GB, 24h. Used in audit log & last-login tooltips. */
export function formatDateTime(date: Date | string | null | undefined): string {
  if (!date) return "—";
  const d = typeof date === "string" ? new Date(date) : date;
  return d.toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

/** "just now" / "5m ago" / "3h ago" / "2d ago", falling back to date for >7 days. */
export function formatRelativeTime(date: Date | string | null | undefined): string {
  if (!date) return "—";
  const then = typeof date === "string" ? new Date(date).getTime() : date.getTime();
  const diff = Date.now() - then;
  if (diff < 0) return formatDate(date);
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return formatDate(date);
}

export function getVarianceDays(targetDate: Date | null, expectedDate: Date | null): number | null {
  if (!targetDate || !expectedDate) return null;
  const diffTime = expectedDate.getTime() - targetDate.getTime();
  return Math.ceil(diffTime / (1000 * 60 * 60 * 24));
}

export function getInitials(name: string | null | undefined): string {
  if (!name) return "?";
  return name
    .split(" ")
    .map((n) => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);
}

/**
 * Convert an ISO 3166-1 alpha-2 country code (e.g. "BE", "FR") to its flag emoji.
 * Returns null for invalid or missing input.
 */
export function countryFlag(code: string | null | undefined): string | null {
  if (!code || code.length !== 2) return null;
  const upper = code.toUpperCase();
  const offset = 0x1f1e6 - 65; // 'A' → regional indicator A
  return String.fromCodePoint(upper.charCodeAt(0) + offset, upper.charCodeAt(1) + offset);
}

/**
 * Parse page & limit from URL search params with safe bounds.
 * Returns `{ page, limit, skip }` ready for Prisma queries.
 */
export function parsePagination(
  searchParams: URLSearchParams,
  { defaultLimit = 50, maxLimit = 100 } = {},
): { page: number; limit: number; skip: number } {
  const page = Math.max(1, Number(searchParams.get("page")) || 1);
  const limit = Math.min(maxLimit, Math.max(1, Number(searchParams.get("limit")) || defaultLimit));
  return { page, limit, skip: (page - 1) * limit };
}

/** Convert a DB user record to the shape expected by UserSelector. */
export function toSelectedUser(
  user: { id: string; name: string; email: string | null; emailVerified: Date | null } | null,
): { id: string; name: string; email: string | null; emailVerified: Date | null } | null {
  if (!user) return null;
  return { id: user.id, name: user.name, email: user.email, emailVerified: user.emailVerified };
}

/** Only allow relative paths to prevent open-redirect attacks. */
export function sanitizeCallbackUrl(
  raw: string | null,
  fallback = "/dashboard",
): string {
  if (!raw) return fallback;
  try {
    const url = new URL(raw, window.location.origin);
    if (url.origin !== window.location.origin) return fallback;
    return url.pathname + url.search;
  } catch {
    return fallback;
  }
}
