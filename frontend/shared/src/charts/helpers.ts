import type { ChartTheme } from "../theme/chartTheme";

export function rgba(hex: string, a: number): string {
  const n = parseInt(hex.replace("#", ""), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
}

export function mix(hexA: string, hexB: string, amount: number): string {
  const a = parseInt(hexA.replace("#", ""), 16);
  const b = parseInt(hexB.replace("#", ""), 16);
  const ch = (s: number): number =>
    Math.round((((a >> s) & 255) * (1 - amount) + ((b >> s) & 255) * amount));
  return `rgb(${ch(16)}, ${ch(8)}, ${ch(0)})`;
}

export function solid(color: string | [string, string]): string {
  return Array.isArray(color) ? color[1] : color;
}

export interface GradientStop {
  offset: number;
  color: string;
}

export interface LinearGradient {
  type: "linear";
  x: number;
  y: number;
  x2: number;
  y2: number;
  colorStops: GradientStop[];
}

export function grad(
  color: string | [string, string],
  x2: number,
  y2: number,
  reverse?: boolean,
): string | LinearGradient {
  if (!Array.isArray(color)) return color;
  const [a, b] = reverse ? [color[1], color[0]] : color;
  return {
    type: "linear",
    x: 0,
    y: 0,
    x2,
    y2,
    colorStops: [
      { offset: 0, color: a },
      { offset: 1, color: b },
    ],
  };
}

export function fade(hex: string, a: number): LinearGradient {
  return {
    type: "linear",
    x: 0,
    y: 0,
    x2: 0,
    y2: 1,
    colorStops: [
      { offset: 0, color: rgba(hex, a) },
      { offset: 1, color: rgba(hex, 0) },
    ],
  };
}

export function niceStep(x: number): number {
  const power = 10 ** Math.floor(Math.log10(x));
  for (const m of [1, 2, 2.5, 5, 10]) {
    if (m * power >= x) return m * power;
  }
  return 10 * power;
}

export function tooltipStyle(
  theme: ChartTheme,
  extra?: Record<string, unknown>,
): Record<string, unknown> {
  return {
    backgroundColor: theme.tooltipBg || "#ffffff",
    borderColor: theme.tooltipBorder || theme.grid,
    borderWidth: 1,
    padding: [8, 12],
    textStyle: { color: theme.text, fontFamily: theme.font, fontSize: 12 },
    extraCssText: `border-radius:10px;box-shadow:0 10px 30px rgba(15,20,30,.10);`,
    ...extra,
  };
}
