import { useEffect, useState } from "react";
import { useThemeStore, type ThemeId } from "../stores/theme";

/** Categorical data-series colors, tuned per theme so charts stay legible against each background. */
const CHART_PALETTES: Record<ThemeId, string[]> = {
  "neon-cyber": ["#00E6E8", "#CF81FF", "#36F1A4", "#FFC200", "#FF6D8A", "#76F1D3"],
  "professional-light": ["#00B593", "#7457D1", "#0092D7", "#E89D00", "#EE0F1F", "#00AC5F"],
  "professional-dark": ["#3FE1BF", "#A494F6", "#00ACF3", "#F2A618", "#F94144", "#1BD79E"],
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
