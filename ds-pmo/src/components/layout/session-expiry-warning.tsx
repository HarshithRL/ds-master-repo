"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Clock, LogIn } from "lucide-react";

const SESSION_MAX_AGE = 8 * 60 * 60; // 8 hours in seconds
const WARN_BEFORE = 10 * 60; // warn 10 minutes before expiry
const WARN_AT = (SESSION_MAX_AGE - WARN_BEFORE) * 1000; // ms after mount

export function SessionExpiryWarning() {
  const router = useRouter();
  const [visible, setVisible] = useState(false);
  const [minutesLeft, setMinutesLeft] = useState(WARN_BEFORE / 60);

  useEffect(() => {
    const warnTimer = setTimeout(() => setVisible(true), WARN_AT);
    return () => clearTimeout(warnTimer);
  }, []);

  // Countdown once visible
  useEffect(() => {
    if (!visible) return;
    const id = setInterval(() => {
      setMinutesLeft((m) => {
        if (m <= 1) {
          clearInterval(id);
          return 0;
        }
        return m - 1;
      });
    }, 60_000);
    return () => clearInterval(id);
  }, [visible]);

  const handleSignIn = useCallback(() => {
    router.push("/login");
  }, [router]);

  if (!visible) return null;

  return (
    <div className="fixed bottom-20 lg:bottom-6 left-1/2 -translate-x-1/2 z-50 animate-page-enter">
      <div className="flex items-center gap-3 px-5 py-3 rounded-lg
                      bg-amber-50/95 dark:bg-amber-900/30 backdrop-blur-md
                      border border-amber-300/50 dark:border-amber-500/20
                      shadow-lg shadow-amber-500/10 dark:shadow-black/30
                      max-w-sm sm:max-w-md">
        <div className="w-8 h-8 rounded-full bg-amber-100 dark:bg-amber-500/15 flex items-center justify-center shrink-0">
          <Clock className="w-4 h-4 text-amber-600 dark:text-amber-400" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-amber-800 dark:text-amber-200">
            Session expiring{minutesLeft > 0 ? ` in ~${minutesLeft} min` : " soon"}
          </p>
          <p className="text-xs text-amber-600 dark:text-amber-400 mt-0.5">
            Save your work and sign in again
          </p>
        </div>
        <button
          onClick={handleSignIn}
          className="shrink-0 flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white bg-etex-orange hover:bg-etex-orange-dark rounded-md transition-colors"
        >
          <LogIn className="w-3.5 h-3.5" />
          Sign in
        </button>
      </div>
    </div>
  );
}
