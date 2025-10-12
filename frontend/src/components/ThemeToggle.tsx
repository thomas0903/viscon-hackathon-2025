import { useEffect, useState } from "react";
import "./ThemeToggle.css";

const STORAGE_KEY = "vis-theme";

function resolveInitialTheme(): boolean {
  if (typeof window === "undefined") return false;
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (stored) {
    return stored === "dark";
  }
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
}

export const ThemeToggle: React.FC = () => {
  const [isDark, setIsDark] = useState<boolean>(resolveInitialTheme);

  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("dark", isDark);
    window.localStorage.setItem(STORAGE_KEY, isDark ? "dark" : "light");
  }, [isDark]);

  useEffect(() => {
    const media = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!media) return;
    const handler = (event: MediaQueryListEvent) => {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      if (stored) return; // respect explicit choice
      setIsDark(event.matches);
    };
    media.addEventListener("change", handler);
    return () => media.removeEventListener("change", handler);
  }, []);

  return (
    <button
      type="button"
      className="theme-toggle"
      aria-label="Toggle dark mode"
      onClick={() => setIsDark((prev) => !prev)}
    >
      <span className="theme-toggle__icon" aria-hidden="true">
        {isDark ? "🌙" : "☀️"}
      </span>
      <span className="theme-toggle__label">{isDark ? "Dark" : "Light"} mode</span>
    </button>
  );
};

export default ThemeToggle;
