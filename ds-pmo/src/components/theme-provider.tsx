"use client";

import { useEffect } from "react";
import { ThemeProvider as NextThemesProvider } from "next-themes";

/**
 * Suppress the React 19 "Encountered a script tag" console error
 * caused by next-themes injecting an inline script to prevent FOUC.
 * This is a known false-positive — the script works correctly during SSR.
 * See: https://github.com/pacocoursey/next-themes/issues/296
 */
function useSuppressThemeScriptWarning() {
  useEffect(() => {
    const originalError = console.error;
    console.error = (...args: unknown[]) => {
      if (
        typeof args[0] === "string" &&
        args[0].includes("Encountered a script tag while rendering React component")
      ) {
        return;
      }
      originalError.apply(console, args);
    };
    return () => {
      console.error = originalError;
    };
  }, []);
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  useSuppressThemeScriptWarning();

  return (
    <NextThemesProvider attribute="class" defaultTheme="light" enableSystem={false}>
      {children}
    </NextThemesProvider>
  );
}
