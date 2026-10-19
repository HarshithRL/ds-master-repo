/**
 * Centralized email templates — Outlook-optimized, spam-safe.
 *
 * Guidelines followed:
 * - Table-based layout (no div-based grids)
 * - All styles inline (no <style> blocks, no shorthand)
 * - MSO conditionals for Outlook rendering
 * - Plain-text alternatives for every email
 * - Minimal links / no image-heavy content to reduce spam score
 * - Consistent From/Reply-To for domain reputation
 * - ETEX brand colors from globals.css
 */

import type {
  OtpCodeData,
  WelcomeUserData,
  ProjectAssignmentData,
  EmailPayload,
} from "./types";

// ---------------------------------------------------------------------------
// ETEX Brand palette (from globals.css)
// ---------------------------------------------------------------------------

const BRAND_PRIMARY = "#E8713A"; // etex-orange
const BRAND_DARK = "#C85A28"; // etex-orange-dark
const BRAND_ACCENT_BG = "#FFF5ED"; // etex-orange-50
const CHARCOAL = "#1A1A2E"; // etex-charcoal — headings
const TEXT_COLOR = "#212529"; // etex-gray-800 — body text
const MUTED_COLOR = "#6C757D"; // etex-gray-500 — secondary text
const BG_COLOR = "#F8F9FA"; // etex-gray-50 — page bg
const CARD_BG = "#ffffff";
const DIVIDER_COLOR = "#E9ECEF"; // etex-gray-200

// ---------------------------------------------------------------------------
// Shared layout
// ---------------------------------------------------------------------------

function layout(title: string, body: string): string {
  return `<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
<head>
<meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<meta name="x-mailer" content="PMO Tracker Notifications" />
<title>${title}</title>
<!--[if mso]>
<noscript>
<xml>
<o:OfficeDocumentSettings>
<o:PixelsPerInch>96</o:PixelsPerInch>
</o:OfficeDocumentSettings>
</xml>
</noscript>
<![endif]-->
</head>
<body style="margin:0; padding:0; background-color:${BG_COLOR}; font-family:Arial, Helvetica, sans-serif; -webkit-text-size-adjust:100%; -ms-text-size-adjust:100%;">
<!--[if mso]>
<table role="presentation" width="600" align="center" cellpadding="0" cellspacing="0" border="0" style="width:600px;">
<tr><td>
<![endif]-->
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:600px; margin:0 auto;">
  <!-- Top accent bar -->
  <tr>
    <td style="height:4px; background-color:${BRAND_PRIMARY}; font-size:1px; line-height:1px;">&nbsp;</td>
  </tr>
  <!-- Header -->
  <tr>
    <td style="background-color:${CARD_BG}; padding:28px 32px 20px 32px; border-bottom:1px solid ${DIVIDER_COLOR};">
      <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
        <tr>
          <td style="font-size:22px; font-weight:bold; color:${CHARCOAL}; font-family:Arial, Helvetica, sans-serif; letter-spacing:-0.3px;">
            <span style="color:${BRAND_PRIMARY};">PMO</span> Tracker
          </td>
        </tr>
      </table>
    </td>
  </tr>
  <!-- Body card -->
  <tr>
    <td style="background-color:${CARD_BG}; padding:32px 32px 28px 32px;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
        <tr>
          <td style="color:${TEXT_COLOR}; font-size:15px; line-height:24px; font-family:Arial, Helvetica, sans-serif;">
            ${body}
          </td>
        </tr>
      </table>
    </td>
  </tr>
  <!-- Footer divider -->
  <tr>
    <td style="background-color:${CARD_BG}; padding:0 32px;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
        <tr>
          <td style="border-top:1px solid ${DIVIDER_COLOR}; font-size:1px; line-height:1px; height:1px;">&nbsp;</td>
        </tr>
      </table>
    </td>
  </tr>
  <!-- Footer -->
  <tr>
    <td style="background-color:${CARD_BG}; padding:20px 32px 28px 32px; text-align:left;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
        <tr>
          <td style="font-size:12px; line-height:18px; color:${MUTED_COLOR}; font-family:Arial, Helvetica, sans-serif;">
            This is an automated notification from PMO Tracker.<br />
            You are receiving this because your email is registered in the system.<br />
            Please do not reply directly to this email.
          </td>
        </tr>
      </table>
    </td>
  </tr>
  <!-- Bottom accent bar -->
  <tr>
    <td style="height:3px; background-color:${BRAND_PRIMARY}; font-size:1px; line-height:1px;">&nbsp;</td>
  </tr>
  <!-- Below-card spacer -->
  <tr>
    <td style="height:24px; font-size:1px; line-height:1px;">&nbsp;</td>
  </tr>
</table>
<!--[if mso]>
</td></tr>
</table>
<![endif]-->
</body>
</html>`;
}

function button(text: string, href: string): string {
  // Bulletproof button: VML for Outlook, CSS for everything else
  return `<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:24px 0 8px 0;">
  <tr>
    <td style="border-radius:4px; background-color:${BRAND_PRIMARY};" align="center">
      <!--[if mso]>
      <v:roundrect xmlns:v="urn:schemas-microsoft-com:vml" xmlns:w="urn:schemas-microsoft-com:office:word" href="${href}" style="height:44px;v-text-anchor:middle;width:220px;" arcsize="10%" strokecolor="${BRAND_DARK}" fillcolor="${BRAND_PRIMARY}">
      <w:anchorlock/>
      <center style="color:#ffffff;font-family:Arial,sans-serif;font-size:15px;font-weight:bold;">
        ${text}
      </center>
      </v:roundrect>
      <![endif]-->
      <!--[if !mso]><!-->
      <a href="${href}" target="_blank" style="display:inline-block; padding:12px 32px; font-size:15px; font-weight:bold; color:#ffffff; text-decoration:none; border-radius:4px; background-color:${BRAND_PRIMARY}; font-family:Arial, Helvetica, sans-serif;">
        ${text}
      </a>
      <!--<![endif]-->
    </td>
  </tr>
</table>`;
}

function infoBox(content: string): string {
  return `<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:16px 0;">
  <tr>
    <td style="background-color:${BRAND_ACCENT_BG}; border-left:3px solid ${BRAND_PRIMARY}; border-radius:2px; padding:14px 18px; font-size:14px; line-height:22px; color:${CHARCOAL}; font-family:Arial, Helvetica, sans-serif;">
      ${content}
    </td>
  </tr>
</table>`;
}

// ---------------------------------------------------------------------------
// OTP Code email (6-digit code to avoid corporate email scanner issues)
// ---------------------------------------------------------------------------

export function otpCodeEmail(data: OtpCodeData): Omit<EmailPayload, "to" | "category"> {
  const digits = data.code.split("");
  const codeBoxes = digits
    .map(
      (d) =>
        `<td style="width:40px; height:48px; text-align:center; vertical-align:middle; font-size:24px; font-weight:bold; font-family:'Courier New', monospace; color:${CHARCOAL}; background-color:${BRAND_ACCENT_BG}; border:1px solid ${DIVIDER_COLOR}; border-radius:6px; letter-spacing:0;">${d}</td>`,
    )
    .join(`<td style="width:6px;">&nbsp;</td>`);

  const html = layout(
    "Your Sign-In Code - PMO App",
    `<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
  <tr>
    <td style="font-size:20px; font-weight:bold; color:${CHARCOAL}; padding-bottom:8px; font-family:Arial, Helvetica, sans-serif;">
      Your sign-in code
    </td>
  </tr>
  <tr>
    <td style="font-size:14px; line-height:22px; color:${MUTED_COLOR}; padding-bottom:24px; font-family:Arial, Helvetica, sans-serif;">
      Enter this code on the login page to access PMO Tracker
    </td>
  </tr>
  <tr>
    <td align="center" style="padding-bottom:24px;">
      <table role="presentation" cellpadding="0" cellspacing="0" border="0">
        <tr>${codeBoxes}</tr>
      </table>
    </td>
  </tr>
  <tr>
    <td>
      ${infoBox("This code expires in 10 minutes and can only be used once.")}
    </td>
  </tr>
  <tr>
    <td style="font-size:12px; line-height:18px; color:${MUTED_COLOR}; padding-top:16px; font-family:Arial, Helvetica, sans-serif;">
      If you didn't request this code, you can safely ignore this email.
    </td>
  </tr>
</table>`,
  );

  const text = `Your sign-in code for PMO Tracker

Your code: ${data.code}

Enter this code on the login page. It expires in 10 minutes and can only be used once.

If you didn't request this code, you can safely ignore this email.

---
PMO Tracker — Automated notification`;

  return { subject: `${data.code} — Your PMO Sign-In Code`, html, text };
}

// ---------------------------------------------------------------------------
// Welcome email (admin creates user)
// ---------------------------------------------------------------------------

export function welcomeEmail(data: WelcomeUserData): Omit<EmailPayload, "to" | "category"> {
  const html = layout(
    "Welcome - PMO Tracker",
    `<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
  <tr>
    <td style="font-size:20px; font-weight:bold; color:${CHARCOAL}; padding-bottom:20px; font-family:Arial, Helvetica, sans-serif;">
      Welcome, ${escapeHtml(data.name)}
    </td>
  </tr>
  <tr>
    <td style="font-size:15px; line-height:24px; color:${TEXT_COLOR}; font-family:Arial, Helvetica, sans-serif;">
      An account has been created for you in PMO Tracker. You can sign in at any time using your email address — no password needed.
    </td>
  </tr>
  <tr>
    <td style="padding-top:8px;">
      ${infoBox("Each time you sign in, you'll receive a one-time code to your email. Just enter it on the login page to access the app.")}
    </td>
  </tr>
  <tr>
    <td>
      ${button("Go to PMO Tracker", data.loginUrl)}
    </td>
  </tr>
  <tr>
    <td style="font-size:12px; line-height:18px; color:${MUTED_COLOR}; padding-top:16px; font-family:Arial, Helvetica, sans-serif;">
      If you have questions, contact your PMO administrator.
    </td>
  </tr>
</table>`,
  );

  const text = `Welcome, ${data.name}

An account has been created for you in PMO Tracker. You can sign in at any time using your email address — no password needed.

Each time you sign in, you'll receive a one-time code to your email. Just enter it on the login page to access the app.

Sign in here: ${data.loginUrl}

If you have questions, contact your PMO administrator.

---
PMO Tracker — Automated notification`;

  return { subject: "Welcome - PMO Tracker", html, text };
}

// ---------------------------------------------------------------------------
// Project assignment notification
// ---------------------------------------------------------------------------

export function projectAssignmentEmail(
  data: ProjectAssignmentData,
): Omit<EmailPayload, "to" | "category"> {
  const roleLabel =
    data.role === "PROJECT_MANAGER" ? "Project Manager" : "PMO";

  const html = layout(
    "Project Assignment - PMO Tracker",
    `<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
  <tr>
    <td style="font-size:20px; font-weight:bold; color:${CHARCOAL}; padding-bottom:20px; font-family:Arial, Helvetica, sans-serif;">
      Project Assignment
    </td>
  </tr>
  <tr>
    <td style="font-size:15px; line-height:24px; color:${TEXT_COLOR}; font-family:Arial, Helvetica, sans-serif;">
      Hi ${escapeHtml(data.recipientName)},<br /><br />
      ${escapeHtml(data.assignedBy)} has assigned you as <strong style="color:${CHARCOAL};">${roleLabel}</strong> on the following project:
    </td>
  </tr>
  <tr>
    <td style="padding:20px 0;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:${BRAND_ACCENT_BG}; border-left:3px solid ${BRAND_PRIMARY}; border-radius:2px;">
        <tr>
          <td style="padding:18px 22px; font-family:Arial, Helvetica, sans-serif;">
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
              <tr>
                <td style="font-size:12px; text-transform:uppercase; letter-spacing:0.5px; color:${MUTED_COLOR}; padding-bottom:4px; font-family:Arial, Helvetica, sans-serif;">Reference</td>
              </tr>
              <tr>
                <td style="font-size:16px; font-weight:bold; color:${CHARCOAL}; padding-bottom:14px; font-family:Arial, Helvetica, sans-serif;">${escapeHtml(data.projectReference)}</td>
              </tr>
              <tr>
                <td style="font-size:12px; text-transform:uppercase; letter-spacing:0.5px; color:${MUTED_COLOR}; padding-bottom:4px; font-family:Arial, Helvetica, sans-serif;">Project Name</td>
              </tr>
              <tr>
                <td style="font-size:16px; font-weight:bold; color:${CHARCOAL}; padding-bottom:14px; font-family:Arial, Helvetica, sans-serif;">${escapeHtml(data.projectName)}</td>
              </tr>
              <tr>
                <td style="font-size:12px; text-transform:uppercase; letter-spacing:0.5px; color:${MUTED_COLOR}; padding-bottom:4px; font-family:Arial, Helvetica, sans-serif;">Your Role</td>
              </tr>
              <tr>
                <td style="font-size:16px; font-weight:bold; color:${BRAND_PRIMARY}; font-family:Arial, Helvetica, sans-serif;">${roleLabel}</td>
              </tr>
            </table>
          </td>
        </tr>
      </table>
    </td>
  </tr>
  <tr>
    <td>
      ${button("View Project", data.projectUrl)}
    </td>
  </tr>
</table>`,
  );

  const text = `Project Assignment

Hi ${data.recipientName},

${data.assignedBy} has assigned you as ${roleLabel} on the following project:

Reference: ${data.projectReference}
Project: ${data.projectName}
Role: ${roleLabel}

View the project: ${data.projectUrl}

---
PMO Tracker — Automated notification`;

  return {
    subject: `Project Assignment: ${data.projectReference} - ${data.projectName}`,
    html,
    text,
  };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
