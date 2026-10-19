/**
 * Email categories. Used to gate sending — e.g. NOTIFICATIONS_DISABLED can
 * mute "notification" emails while keeping "auth" (login OTPs) flowing.
 *
 *   - "auth":         critical auth flows (OTP / magic link). Never gated.
 *   - "notification": informational (welcome, assignment, etc.). Gateable.
 */
export type EmailCategory = "auth" | "notification";

export interface EmailPayload {
  to: string | string[];
  subject: string;
  html: string;
  text: string;
  category: EmailCategory;
}

export interface OtpCodeData {
  code: string;
  email: string;
}

export interface WelcomeUserData {
  name: string;
  email: string;
  loginUrl: string;
}

export interface ProjectAssignmentData {
  recipientName: string;
  projectName: string;
  projectReference: string;
  role: string;
  projectUrl: string;
  assignedBy: string;
}
