"use client";

import { useEffect, useState } from "react";

/* ── Greeting by time of day ────────────────────────────────────── */

function getGreeting(): string {
  const h = new Date().getHours();
  if (h < 5) return "Burning the midnight oil";
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  if (h < 21) return "Good evening";
  return "Working late";
}

/* ── Rotating one-liners — light, PMO-flavoured ─────────────────── */

const ONE_LINERS = [
  "Let's move some gates forward today.",
  "Your portfolio awaits.",
  "Time to check those milestones.",
  "Another day, another baseline.",
  "Let's keep things on track.",
  "Ready to review the numbers?",
  "Your projects missed you.",
  "Governance never sleeps.",
  "Let's turn risks into mitigations.",
  "Dashboard is fresh and ready.",
];

function pickOneLiner(): string {
  return ONE_LINERS[Math.floor(Math.random() * ONE_LINERS.length)];
}

/* ── Session key — show once per browser session ────────────────── */

const SESSION_KEY = "pmo-welcome-shown";

/* ═══════════════════════════════════════════════════════════════════
   WelcomeToast
   Slides down from the top, stays ~4s, then fades out.
   Only shows once per session.
   ═══════════════════════════════════════════════════════════════════ */

export function WelcomeToast({ userName }: { userName: string | null }) {
  const [visible, setVisible] = useState(false);
  const [leaving, setLeaving] = useState(false);

  const firstName = userName?.split(" ")[0] || "there";

  useEffect(() => {
    // Only show once per session
    if (sessionStorage.getItem(SESSION_KEY)) return;
    sessionStorage.setItem(SESSION_KEY, "1");

    // Small delay so the page settles first
    const showTimer = setTimeout(() => setVisible(true), 400);

    // Start exit animation after 4.5s
    const exitTimer = setTimeout(() => setLeaving(true), 4900);

    // Remove from DOM after exit animation completes
    const hideTimer = setTimeout(() => setVisible(false), 5600);

    return () => {
      clearTimeout(showTimer);
      clearTimeout(exitTimer);
      clearTimeout(hideTimer);
    };
  }, []);

  if (!visible) return null;

  return (
    <div
      className={`
        fixed top-16 left-1/2 -translate-x-1/2 z-50 pointer-events-none
        transition-all duration-700 ease-out
        ${leaving
          ? "opacity-0 -translate-y-3 scale-95"
          : "opacity-100 translate-y-2 scale-100"
        }
      `}
    >
      <div className="pointer-events-auto flex items-center gap-4 px-6 py-4 rounded-xl
                      bg-white/98 dark:bg-[#1A1D23]/98 backdrop-blur-xl
                      border border-gray-200/60 dark:border-gray-700/40
                      shadow-xl shadow-black/8 dark:shadow-black/40
                      ring-1 ring-black/3 dark:ring-white/4
                      max-w-sm sm:max-w-md">
        {/* Accent bar */}
        <div className="w-0.5 h-9 rounded-full bg-linear-to-b from-etex-orange to-etex-orange/40 shrink-0" />

        <div className="min-w-0">
          <p className="text-sm font-semibold text-etex-charcoal dark:text-gray-100 tracking-tight truncate">
            {getGreeting()}, {firstName}
          </p>
          <p className="text-xs text-etex-gray-500 dark:text-gray-400 truncate mt-0.5 font-light tracking-wide">
            {pickOneLiner()}
          </p>
        </div>
      </div>
    </div>
  );
}
