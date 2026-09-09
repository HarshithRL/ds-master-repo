import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

export const THEME_STORAGE_KEY = "mate-theme";
export const THEME_PREFERENCES = ["light", "system", "dark"];

const ThemeContext = createContext(null);

function getSystemTheme() {
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

function resolveTheme(preference) {
  return preference === "system" ? getSystemTheme() : preference;
}

function readStoredPreference() {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    if (THEME_PREFERENCES.includes(stored)) {
      return stored;
    }
  } catch {
    /* ignore */
  }
  return "system";
}

function applyThemeAttributes(preference, resolved) {
  document.documentElement.setAttribute("data-theme", resolved);
  document.documentElement.setAttribute("data-theme-preference", preference);
  document.documentElement.classList.toggle("dark", resolved === "dark");
}

export function ThemeProvider({ children }) {
  const [preference, setPreferenceState] = useState(readStoredPreference);
  const [resolvedTheme, setResolvedTheme] = useState(() =>
    resolveTheme(readStoredPreference())
  );

  const setPreference = useCallback((next) => {
    if (!THEME_PREFERENCES.includes(next)) {
      return;
    }

    setPreferenceState(next);

    try {
      localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      /* ignore */
    }

    const resolved = resolveTheme(next);
    setResolvedTheme(resolved);
    applyThemeAttributes(next, resolved);
  }, []);

  useEffect(() => {
    const resolved = resolveTheme(preference);
    setResolvedTheme(resolved);
    applyThemeAttributes(preference, resolved);

    if (preference !== "system") {
      return undefined;
    }

    const media = window.matchMedia("(prefers-color-scheme: dark)");

    const onChange = () => {
      const nextResolved = getSystemTheme();
      setResolvedTheme(nextResolved);
      applyThemeAttributes("system", nextResolved);
    };

    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [preference]);

  const value = useMemo(
    () => ({
      preference,
      resolvedTheme,
      setPreference,
    }),
    [preference, resolvedTheme, setPreference]
  );

  return (
    <ThemeContext.Provider value={value}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const context = useContext(ThemeContext);

  if (!context) {
    throw new Error("useTheme must be used within ThemeProvider");
  }

  return context;
}
