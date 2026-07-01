import { useEffect, useState } from "react";
import { useThemeStore, type ThemeId } from "../stores/theme";

/** Categorical data-series colors, tuned per theme so charts stay legible against each background. */
const CHART_PALETTES: Record<ThemeId, string[]> = {
  "neon-cyber": ["#28E0C2", "#7C3AED", "#00E5B8", "#5CEBD4", "#A78BFA", "#22D3EE"],
  "professional-light": ["#2563EB", "#059669", "#4F46E5", "#0EA5E9", "#7C3AED", "#0D9488"],
  "professional-dark": ["#22D3EE", "#818CF8", "#A78BFA", "#38BDF8", "#C084FC", "#2DD4BF"],
};

/** Chrome colors (grid lines, axis ticks, tooltip surface) resolved from the live theme CSS variables. */
export function useChartChrome() {
  const theme = useThemeStore((s) => s.theme);
  const [chrome, setChrome] = useState(() => readChartChrome());

  useEffect(() => {
    setChrome(readChartChrome());
  }, [theme]);

  return chrome;
}

function readChartChrome() {
  const styles = getComputedStyle(document.documentElement);
  const rgb = (name: string) => `rgb(${styles.getPropertyValue(name).trim().split(/\s+/).join(" ")})`;
  return {
    grid: rgb("--color-border-subtle"),
    axis: rgb("--color-tx-muted"),
    tooltipBg: rgb("--color-app-card"),
    tooltipBorder: rgb("--color-border"),
    text: rgb("--color-tx-primary"),
    bg: rgb("--color-app-bg"),
    brand: rgb("--color-brand"),
    primary: rgb("--color-primary"),
  };
}

export function useChartPalette(): string[] {
  const theme = useThemeStore((s) => s.theme);
  return CHART_PALETTES[theme];
}
