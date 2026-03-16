import { create } from "zustand";

type Theme = "light" | "dark" | "system";

interface ThemeState {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
}

function loadTheme(): Theme {
  try {
    const stored = localStorage.getItem("app-theme");
    if (stored === "light" || stored === "dark" || stored === "system")
      return stored;
  } catch {
    // ignore
  }
  return "system";
}

export const useThemeStore = create<ThemeState>((set, get) => ({
  theme: loadTheme(),

  setTheme: (theme) => {
    localStorage.setItem("app-theme", theme);
    set({ theme });
  },

  toggleTheme: () => {
    const current = get().theme;
    const next: Theme =
      current === "light" ? "dark" : current === "dark" ? "system" : "light";
    localStorage.setItem("app-theme", next);
    set({ theme: next });
  },
}));
