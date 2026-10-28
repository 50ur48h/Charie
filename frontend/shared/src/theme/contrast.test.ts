import { readFileSync } from "node:fs";
import { describe, expect, test } from "vitest";
import { contrastRatio } from "./contrast";

type ThemeVars = Record<string, string>;

const THEMES = ["sage", "lavender", "mist", "seafoam", "mauve", "slate"] as const;

function readThemes(): Record<string, ThemeVars> {
  // Vitest runs with frontend/ as its working directory.
  const css = readFileSync("shared/src/theme/themes.css", "utf-8");
  const out: Record<string, ThemeVars> = {};
  const blocks = css.matchAll(/:root(?:\[data-theme="([^"]+)"\])?\s*\{([^}]*)\}/g);
  for (const block of blocks) {
    const name = block[1] ?? "sage";
    const vars: ThemeVars = {};
    const pairs = block[2].matchAll(/--([\w-]+)\s*:\s*(#[0-9a-fA-F]{3,6})/g);
    for (const pair of pairs) {
      vars[pair[1]] = pair[2];
    }
    out[name] = vars;
  }
  return out;
}

const byTheme = readThemes();

// [text variable, background variable]
const TEXT_PAIRS: [string, string][] = [
  ["text", "bg"],
  ["text", "surface"],
  ["text", "sidebar"],
  ["text", "surface-2"],
  ["text", "bubble"],
  ["text-2", "bg"],
  ["text-2", "surface"],
  ["text-2", "sidebar"],
  ["text-2", "surface-2"],
  ["prose", "bg"],
  ["prose", "surface"],
  ["muted", "bg"],
  ["muted", "surface"],
  ["muted", "sidebar"],
  ["muted", "surface-2"],
  ["accent-ink", "accent-soft"],
  ["accent-ink", "surface"],
  ["accent-ink", "bg"],
  ["good-ink", "good-soft"],
  ["bad-ink", "bad-soft"],
  ["warn-ink", "warn-soft"],
  ["code-ink", "code-bg"],
  ["code-kw", "code-bg"],
  ["code-str", "code-bg"],
  ["chart-muted", "surface"],
  ["bad-ink", "surface"],
  ["good-ink", "surface"],
  ["white", "accent"],
  ["white", "bad-ink"],
];

// Pairs the owner explicitly accepted below AA (with the reason).
// Format: "theme:text on background".
const KNOWN_EXCEPTIONS: string[] = [
  // Task 2 answer goes here when it lands.
];

const FOCUS_PAIRS: [string, string][] = [
  ["accent", "bg"],
  ["accent", "surface"],
  ["accent", "sidebar"],
];

function ratio(theme: string, text: string, background: string): number {
  const vars = byTheme[theme];
  const fg = text === "white" ? "#FFFFFF" : vars[text];
  const bg = vars[background];
  if (!fg || !bg) throw new Error(`missing variable in ${theme}: ${text} on ${background}`);
  return contrastRatio(fg, bg);
}

describe("contrast", () => {
  test("contrastRatio matches known values", () => {
    expect(contrastRatio("#000000", "#FFFFFF")).toBeCloseTo(21, 1);
    expect(contrastRatio("#FFFFFF", "#000000")).toBeCloseTo(21, 1);
    expect(contrastRatio("#6E9277", "#6E9277")).toBeCloseTo(1, 2);
  });

  test("text pairs reach 4.5:1 in every theme", () => {
    const failures: string[] = [];
    for (const theme of THEMES) {
      for (const [text, background] of TEXT_PAIRS) {
        const key = `${theme}:${text} on ${background}`;
        if (KNOWN_EXCEPTIONS.includes(key)) continue;
        const value = ratio(theme, text, background);
        if (value < 4.5) failures.push(`${key} is ${value.toFixed(2)}:1`);
      }
    }
    expect(failures).toEqual([]);
  });

  test("the accent reaches 3:1 for focus rings in every theme", () => {
    const failures: string[] = [];
    for (const theme of THEMES) {
      for (const [text, background] of FOCUS_PAIRS) {
        const key = `${theme}:${text} on ${background}`;
        if (KNOWN_EXCEPTIONS.includes(key)) continue;
        const value = ratio(theme, text, background);
        if (value < 3) failures.push(`${key} is ${value.toFixed(2)}:1`);
      }
    }
    expect(failures).toEqual([]);
  });
});
