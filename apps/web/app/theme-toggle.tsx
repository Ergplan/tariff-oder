"use client";

import { useEffect, useState } from "react";

type Theme = "light" | "dark";

/**
 * Day and night mode (increment 52).  The choice is kept in a "theme" cookie so the server renders
 * the page in it from the first paint; without a choice the page follows the system's preference.
 */
export default function ThemeToggle({ initial }: { initial?: Theme }) {
  const [theme, setTheme] = useState<Theme | undefined>(initial);
  useEffect(() => {
    if (theme) return;
    setTheme(window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
  }, [theme]);
  function choose(t: Theme) {
    setTheme(t);
    document.documentElement.dataset.theme = t;
    document.cookie = `theme=${t}; path=/; max-age=31536000; samesite=lax`;
  }
  return (
    <span className="theme-toggle" role="group" aria-label="Colour theme">
      <button type="button" aria-pressed={theme === "light"} onClick={() => choose("light")}>
        Day
      </button>
      <button type="button" aria-pressed={theme === "dark"} onClick={() => choose("dark")}>
        Night
      </button>
    </span>
  );
}
