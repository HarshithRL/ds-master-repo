/**
 * Centralized email service.
 *
 * - Production: sends via Resend API
 * - Debug (non-production): redirects ALL emails to EMAIL_DEBUG_TO
 *   (or logs to console if that isn't set)
 *
 * Usage:
 *   import { sendEmail } from "@/lib/email";
 *   await sendEmail({ to: "user@etexgroup.com", subject, html, text });
 */

import { Resend } from "resend";
import type { EmailPayload } from "./types";

// Re-export templates for convenient imports
export {
  otpCodeEmail,
  welcomeEmail,
  projectAssignmentEmail,
} from "./templates";
export type {
  EmailCategory,
  EmailPayload,
  OtpCodeData,
  WelcomeUserData,
  ProjectAssignmentData,
} from "./types";

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const RESEND_API_KEY = process.env.AUTH_RESEND_KEY;
const FROM_ADDRESS =
  process.env.EMAIL_FROM || "ETEX PMO <noreply@etexgroup.com>";
const IS_PRODUCTION = process.env.NODE_ENV === "production";
const DEBUG_RECIPIENT = process.env.EMAIL_DEBUG_TO;

// Temporary kill-switch: when "true", only "auth"-category emails are sent.
// All "notification" emails are dropped (logged, no Resend call).
function notificationsDisabled(): boolean {
  return process.env.EMAIL_NOTIFICATIONS_DISABLED === "true";
}

// Lazy-initialized Resend client
let _resend: Resend | null = null;
function getResend(): Resend {
  if (!_resend) {
    if (!RESEND_API_KEY) {
      throw new Error("AUTH_RESEND_KEY is not configured");
    }
    _resend = new Resend(RESEND_API_KEY);
  }
  return _resend;
}

// ---------------------------------------------------------------------------
// Core send function
// ---------------------------------------------------------------------------

export interface SendResult {
  success: boolean;
  id?: string;
  error?: string;
  debugRedirected?: boolean;
  skipped?: "notifications_disabled";
}

export async function sendEmail(payload: EmailPayload): Promise<SendResult> {
  // --- Kill-switch: drop non-auth emails when notifications are disabled ---
  if (payload.category !== "auth" && notificationsDisabled()) {
    const to = Array.isArray(payload.to) ? payload.to.join(", ") : payload.to;
    console.info(
      `[email] Skipped (notifications disabled): "${payload.subject}" → ${to}`,
    );
    return { success: true, skipped: "notifications_disabled" };
  }

  const originalTo = Array.isArray(payload.to)
    ? payload.to
    : [payload.to];

  // --- Debug mode: redirect to debug recipient, or send normally ---
  if (!IS_PRODUCTION && DEBUG_RECIPIENT) {
    return sendViaResend({
      ...payload,
      to: DEBUG_RECIPIENT,
      subject: `[DEBUG → ${originalTo.join(", ")}] ${payload.subject}`,
    });
  }

  // --- Production (or debug without EMAIL_DEBUG_TO): send normally ---
  return sendViaResend(payload);
}

// ---------------------------------------------------------------------------
// Send multiple emails (fire-and-forget, non-blocking)
// ---------------------------------------------------------------------------

export function sendEmailAsync(payload: EmailPayload): void {
  sendEmail(payload).catch((err) => {
    console.error("[email] Failed to send:", err);
  });
}

// ---------------------------------------------------------------------------
// Resend transport
// ---------------------------------------------------------------------------

async function sendViaResend(payload: EmailPayload): Promise<SendResult> {
  try {
    const resend = getResend();
    const to = Array.isArray(payload.to) ? payload.to : [payload.to];

    const { data, error } = await resend.emails.send({
      from: FROM_ADDRESS,
      to,
      subject: payload.subject,
      html: payload.html,
      text: payload.text,
    });

    if (error) {
      console.error("[email] Resend error:", error);
      return { success: false, error: error.message };
    }

    return { success: true, id: data?.id };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    console.error("[email] Send failed:", message);
    return { success: false, error: message };
  }
}
