import { THEME_PREFERENCES, useTheme } from "./ThemeProvider";
import "./theme-toggle.css";

const LABELS = {
  light: "Light",
  system: "System",
  dark: "Dark",
};

function ThemeToggle({ className = "" }) {
  const { preference, setPreference } = useTheme();

  return (
    <div
      className={`theme-toggle ${className}`.trim()}
      role="group"
      aria-label="Appearance"
    >
      {THEME_PREFERENCES.map((mode) => (
        <button
          key={mode}
          type="button"
          className={`theme-toggle-btn${preference === mode ? " active" : ""}`}
          aria-pressed={preference === mode}
          onClick={() => setPreference(mode)}
        >
          {LABELS[mode]}
        </button>
      ))}
    </div>
  );
}

export default ThemeToggle;
