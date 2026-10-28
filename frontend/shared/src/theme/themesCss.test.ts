import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, test } from "vitest";

function themesCssPath(): string {
  try {
    return fileURLToPath(new URL("./themes.css", import.meta.url));
  } catch {
    // import.meta.url has no file scheme under some runners: resolve from the
    // frontend root instead (`npm test` always runs there).
    return join(process.cwd(), "shared", "src", "theme", "themes.css");
  }
}

const themesCss = readFileSync(themesCssPath(), "utf8");

const EXPECTED_VARIABLES = [
  "--bg",
  "--sidebar",
  "--surface",
  "--surface-2",
  "--border",
  "--border-soft",
  "--text",
  "--text-2",
  "--prose",
  "--muted",
  "--muted-2",
  "--placeholder",
  "--accent",
  "--accent-ink",
  "--accent-soft",
  "--accent-hover",
  "--bubble",
  "--head-hover",
  "--focus",
  "--shadow-rgb",
  "--good",
  "--good-ink",
  "--good-soft",
  "--bad",
  "--bad-ink",
  "--bad-soft",
  "--warn",
  "--warn-ink",
  "--warn-soft",
  "--code-bg",
  "--code-ink",
  "--code-kw",
  "--code-str",
  "--chart-pos",
  "--chart-neg",
  "--chart-grid",
  "--chart-muted",
  "--chart-edge",
];

function blockVariables(css: string, selector: string): string[] {
  const start = css.indexOf(selector);
  if (start < 0) return [];
  const open = css.indexOf("{", start);
  const close = css.indexOf("}", open);
  const block = css
    .slice(open + 1, close)
    .replace(/\/\*[\s\S]*?\*\//g, '');
  return block
    .split(";")
    .map((part) => part.trim())
    .filter((part) => part.startsWith("--"))
    .map((part) => part.slice(0, part.indexOf(":")).trim());
}

describe("themes.css", () => {
  test("has the Sage block and 5 data-theme blocks", () => {
    expect(themesCss).toContain(":root {");
    for (const key of ["lavender", "mist", "seafoam", "mauve", "slate"]) {
      expect(themesCss).toContain(`:root[data-theme="${key}"] {`);
    }
  });

  test("each data-theme block sets the same 38 variables as Sage", () => {
    // Sage's :root also holds 6 font, size and radius variables after the colors.
    const sage = blockVariables(themesCss, ":root {");
    expect(sage).toEqual([
      ...EXPECTED_VARIABLES,
      "--radius",
      "--radius-sm",
      "--font",
      "--font-prose",
      "--font-mono",
      "--prose-size",
    ]);
    for (const key of ["lavender", "mist", "seafoam", "mauve", "slate"]) {
      expect(blockVariables(themesCss, `:root[data-theme="${key}"] {`)).toEqual(
        EXPECTED_VARIABLES,
      );
    }
  });

  test("Sage's accent is #5D7C65", () => {
    expect(themesCss).toMatch(/:root \{\s*[^}]*--accent: #5D7C65;/);
  });
});
