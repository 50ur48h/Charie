import { useEffect, useState } from "react";

export type ThemeKey = "sage" | "lavender" | "mist" | "seafoam" | "mauve" | "slate";

export const THEMES: { key: ThemeKey; name: string }[] = [
  { key: "sage", name: "Sage" },
  { key: "lavender", name: "Lavender" },
  { key: "mist", name: "Mist" },
  { key: "seafoam", name: "Seafoam" },
  { key: "mauve", name: "Mauve" },
  { key: "slate", name: "Slate" },
];

export const DEFAULT_THEME: ThemeKey = "sage";
export const THEME_STORAGE_KEY = "charie-theme";
export const THEME_CHANGE_EVENT = "themechange";

export function isThemeKey(value: unknown): value is ThemeKey {
  return THEMES.some((t) => t.key === value);
}

export function readSavedTheme(): ThemeKey {
  try {
    const saved = localStorage.getItem(THEME_STORAGE_KEY);
    if (isThemeKey(saved)) return saved;
  } catch {
    // localStorage unavailable (private mode): fall through to the default.
  }
  return DEFAULT_THEME;
}

export function getTheme(): ThemeKey {
  const key = document.documentElement.dataset.theme;
  return isThemeKey(key) ? key : DEFAULT_THEME;
}

export function setTheme(key: ThemeKey): void {
  document.documentElement.dataset.theme = key;
  try {
    localStorage.setItem(THEME_STORAGE_KEY, key);
  } catch {
    // Ignore write failures; the page still recolors.
  }
  window.dispatchEvent(new CustomEvent<ThemeKey>(THEME_CHANGE_EVENT, { detail: key }));
}

export function useTheme(): [ThemeKey, (key: ThemeKey) => void] {
  const [theme, setCurrent] = useState<ThemeKey>(getTheme);
  useEffect(() => {
    const onChange = (event: Event) => {
      setCurrent((event as CustomEvent<ThemeKey>).detail);
    };
    window.addEventListener(THEME_CHANGE_EVENT, onChange);
    return () => window.removeEventListener(THEME_CHANGE_EVENT, onChange);
  }, []);
  return [theme, setTheme];
}
