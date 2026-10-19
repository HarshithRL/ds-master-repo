/**
 * Thin wrapper around sonner — keeps every component on the same toast API
 * even if we swap the underlying library later. Adds consistent durations,
 * a single notify-once helper for save-failed flows, and an `apiError` parser
 * that pulls the message off a fetch Response or Error object.
 */

import { toast as sonner } from "sonner";

const SHORT = 2500;
const LONG = 5000;

export const toast = {
  success(message: string, opts?: { description?: string }) {
    sonner.success(message, { description: opts?.description, duration: SHORT });
  },
  info(message: string, opts?: { description?: string }) {
    sonner.info(message, { description: opts?.description, duration: SHORT });
  },
  warning(message: string, opts?: { description?: string }) {
    sonner.warning(message, { description: opts?.description, duration: LONG });
  },
  error(message: string, opts?: { description?: string }) {
    sonner.error(message, { description: opts?.description, duration: LONG });
  },
  /** Shows a single error toast keyed by `id` — repeated calls replace it. */
  errorOnce(id: string, message: string, opts?: { description?: string }) {
    sonner.error(message, { id, description: opts?.description, duration: LONG });
  },
  /** Dismiss a toast (or all if no id given). */
  dismiss(id?: string) {
    sonner.dismiss(id);
  },
  /** Lifecycle helper for long-running operations. */
  promise<T>(
    promise: Promise<T>,
    msgs: { loading: string; success: string; error: string },
  ) {
    return sonner.promise(promise, msgs);
  },
};

/**
 * Pull a human message out of an unknown error / fetch response and surface it
 * with toast.error. Returns the parsed message so callers can do something else
 * with it too (e.g. log it).
 */
export async function reportApiError(err: unknown, fallback = "Something went wrong"): Promise<string> {
  let msg = fallback;
  try {
    if (err instanceof Response) {
      const body = await err.clone().json().catch(() => null);
      msg = body?.error || body?.message || `${err.status} ${err.statusText}` || fallback;
    } else if (err instanceof Error) {
      msg = err.message || fallback;
    } else if (typeof err === "string") {
      msg = err;
    }
  } catch {
    msg = fallback;
  }
  toast.error(msg);
  return msg;
}
