import { useEffect, useState } from "react";

const colorVariables = [
  "--color-graph-bg",
  "--color-graph-guide",
  "--color-graph-label",
  "--color-graph-node-label",
  "--color-graph-node-poster-outline",
  "--color-graph-node-outline",
  "--color-graph-legend-bg",
  "--color-graph-legend-border",
  "--color-graph-legend-shadow",
  "--color-graph-legend-header",
  "--color-graph-legend-body",
  "--color-graph-legend-chip-bg",
  "--color-graph-legend-chip-border",
] as const;

type ColorVariable = typeof colorVariables[number];
type ThemeColors = Record<ColorVariable, string>;

function getThemeColors(element: HTMLElement): ThemeColors {
  const styles = getComputedStyle(element);
  const colors = {} as ThemeColors;
  for (const name of colorVariables) {
    colors[name] = styles.getPropertyValue(name).trim();
  }
  return colors;
}

export function useThemeColors(ref: any) {
  const [colors, setColors] = useState<ThemeColors | null>(null);

  useEffect(() => {
    if (!ref.current) return;

    // Initial read
    setColors(getThemeColors(ref.current));

    // Observe for theme changes (toggling 'dark' class on <html>)
    const observer = new MutationObserver(() => {
      if (ref.current) {
        setColors(getThemeColors(ref.current));
      }
    });

    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });

    return () => observer.disconnect();
  }, [ref]);

  return colors;
}