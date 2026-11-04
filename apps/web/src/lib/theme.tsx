"use client";

/** How Charie looks in this browser: a palette and light or dark (D-046). */

import { useCallback, useEffect, useMemo, useSyncExternalStore } from "react";

import { createPersisted } from "./persisted";
import { PALETTE_STORAGE_KEY, THEME_STORAGE_KEY } from "./theme-keys";

export type Theme = "light" | "dark";

/** Shared with the pre-paint script in `layout.tsx` (see `theme-keys.ts`). */
export { PALETTE_STORAGE_KEY, THEME_STORAGE_KEY };

export const PALETTES = [
  { key: "sage", name: "Sage", accent: "#6e9277", bg: "#f4f6f1" },
  { key: "lavender", name: "Lavender", accent: "#8a7fc4", bg: "#f6f5fa" },
  { key: "mist", name: "Mist", accent: "#6286b0", bg: "#f3f6f9" },
  { key: "seafoam", name: "Seafoam", accent: "#5a9e96", bg: "#f2f7f6" },
  { key: "mauve", name: "Mauve", accent: "#a97887", bg: "#f9f5f6" },
  { key: "slate", name: "Slate", accent: "#5f6b7a", bg: "#f5f5f4" },
  { key: "clay", name: "Clay", accent: "#c4673a", bg: "#f6f3ee" },
] as const;

export type Palette = (typeof PALETTES)[number]["key"];

function isTheme(value: string): value is Theme {
  return value === "light" || value === "dark";
}

function isPalette(value: string): value is Palette {
  return PALETTES.some((palette) => palette.key === value);
}

const themeStore = createPersisted<Theme>(THEME_STORAGE_KEY, "light", isTheme);
const paletteStore = createPersisted<Palette>(PALETTE_STORAGE_KEY, "sage", isPalette);

function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  // Light is the absence of the attribute, so there is one representation of it.
  if (theme === "dark") root.setAttribute("data-theme", "dark");
  else root.removeAttribute("data-theme");
}

function applyPalette(palette: Palette): void {
  const root = document.documentElement;
  if (palette === "sage") root.removeAttribute("data-palette");
  else root.setAttribute("data-palette", palette);
}

export interface ThemeChoice {
  theme: Theme;
  setTheme: (next: Theme) => void;
  toggle: () => void;
}

export function useTheme(): ThemeChoice {
  const theme = useSyncExternalStore(themeStore.subscribe, themeStore.get, themeStore.getServer);

  const setTheme = useCallback((next: Theme) => {
    themeStore.set(next);
  }, []);

  // Keyed on the value rather than done inside `setTheme`, so a change made in another tab.
  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  return useMemo(
    () => ({ theme, setTheme, toggle: () => setTheme(theme === "dark" ? "light" : "dark") }),
    [theme, setTheme],
  );
}

export interface PaletteChoice {
  palette: Palette;
  setPalette: (next: Palette) => void;
}

export function usePalette(): PaletteChoice {
  const palette = useSyncExternalStore(
    paletteStore.subscribe,
    paletteStore.get,
    paletteStore.getServer,
  );

  const setPalette = useCallback((next: Palette) => {
    paletteStore.set(next);
  }, []);

  useEffect(() => {
    applyPalette(palette);
  }, [palette]);

  return useMemo(() => ({ palette, setPalette }), [palette, setPalette]);
}

/** Subscribe to palette and mode changes made anywhere on the page. */
export function useAppearanceVersion(): string {
  const theme = useSyncExternalStore(themeStore.subscribe, themeStore.get, themeStore.getServer);
  const palette = useSyncExternalStore(
    paletteStore.subscribe,
    paletteStore.get,
    paletteStore.getServer,
  );
  return `${palette}:${theme}`;
}
