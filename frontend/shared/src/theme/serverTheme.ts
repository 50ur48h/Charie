import { getTheme, isThemeKey, setTheme } from "./theme";

// Applies the theme the server saved, after /api/me loads. Unknown values
// leave the browser's theme alone (reading it falls back to sage).
export function applyServerTheme(theme: unknown): void {
  if (!isThemeKey(theme)) return;
  if (theme === getTheme()) return;
  setTheme(theme);
}
