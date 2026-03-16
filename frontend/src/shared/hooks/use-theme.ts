import { useEffect } from "react";
import { useThemeStore } from "@/shared/stores/theme-store";

/** Syncs the theme store to the DOM. Call once in App.tsx. */
export function useTheme() {
  const theme = useThemeStore((s) => s.theme);

  useEffect(() => {
    const root = document.documentElement;

    function apply(resolved: "light" | "dark") {
      root.setAttribute("data-theme", resolved);
    }

    if (theme === "light" || theme === "dark") {
      apply(theme);
      return;
    }

    // theme === "system" — match OS preference
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    apply(mq.matches ? "dark" : "light");

    function onChange(e: MediaQueryListEvent) {
      apply(e.matches ? "dark" : "light");
    }

    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [theme]);
}
