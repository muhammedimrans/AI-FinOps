import { create } from "zustand";

export type ThemeId = "neon-cyber" | "professional-light" | "professional-dark";

export const THEMES: { id: ThemeId; label: string; description: string }[] = [
  { id: "neon-cyber", label: "Neon Cyber", description: "Teal glow, glass surfaces" },
  { id: "professional-light", label: "Professional Light", description: "Clean, enterprise-ready" },
  { id: "professional-dark", label: "Professional Dark", description: "Charcoal, high contrast" },
];

const STORAGE_KEY = "costorah-theme";

function isThemeId(value: string | null): value is ThemeId {
  return value === "neon-cyber" || value === "professional-light" || value === "professional-dark";
}

/** Reads the theme the blocking inline script in index.html already applied to <html>, avoiding a flash. */
function getInitialTheme(): ThemeId {
  if (typeof document !== "undefined") {
    const attr = document.documentElement.getAttribute("data-theme");
    if (isThemeId(attr)) return attr;
  }
  if (typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches) {
    return "professional-dark";
  }
  return "professional-light";
}

interface ThemeState {
  theme: ThemeId;
  setTheme: (theme: ThemeId) => void;
}

export const useThemeStore = create<ThemeState>()((set) => ({
  theme: getInitialTheme(),
  setTheme: (theme) => {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      // Storage unavailable (private browsing, quota) — theme still applies for this session.
    }
    set({ theme });
  },
}));
