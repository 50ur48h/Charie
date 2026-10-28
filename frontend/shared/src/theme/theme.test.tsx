import { act, cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";
import {
  DEFAULT_THEME,
  getTheme,
  isThemeKey,
  readSavedTheme,
  setTheme,
  THEME_CHANGE_EVENT,
  THEME_STORAGE_KEY,
  THEMES,
  useTheme,
} from "./theme";

afterEach(() => {
  cleanup();
  localStorage.clear();
  delete document.documentElement.dataset.theme;
});

describe("theme switcher", () => {
  test("setTheme sets data-theme on the html element", () => {
    setTheme("mauve");
    expect(document.documentElement.dataset.theme).toBe("mauve");
  });

  test("setTheme saves the theme as charie-theme", () => {
    setTheme("slate");
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("slate");
    expect(localStorage.getItem("charie-theme")).toBe("slate");
  });

  test("setTheme sends a themechange event with the theme", () => {
    const seen: string[] = [];
    const onChange = (event: Event) => {
      seen.push((event as CustomEvent<string>).detail);
    };
    window.addEventListener(THEME_CHANGE_EVENT, onChange);
    setTheme("mist");
    window.removeEventListener(THEME_CHANGE_EVENT, onChange);
    expect(seen).toEqual(["mist"]);
  });

  test("readSavedTheme loads a saved theme", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "seafoam");
    expect(readSavedTheme()).toBe("seafoam");
  });

  test("readSavedTheme falls back to sage for a missing or unknown theme", () => {
    expect(readSavedTheme()).toBe("sage");
    localStorage.setItem(THEME_STORAGE_KEY, "ultraviolet");
    expect(readSavedTheme()).toBe("sage");
  });

  test("getTheme falls back to sage without data-theme", () => {
    expect(getTheme()).toBe(DEFAULT_THEME);
  });

  test("isThemeKey accepts only the 6 theme keys", () => {
    expect(THEMES.map((t) => t.key)).toEqual([
      "sage",
      "lavender",
      "mist",
      "seafoam",
      "mauve",
      "slate",
    ]);
    expect(isThemeKey("sage")).toBe(true);
    expect(isThemeKey("nope")).toBe(false);
  });

  test("useTheme updates when the theme changes", () => {
    function Probe() {
      const [theme, set] = useTheme();
      return (
        <button type="button" onClick={() => set("lavender")}>
          {theme}
        </button>
      );
    }
    const { getByRole } = render(<Probe />);
    expect(getByRole("button").textContent).toBe("sage");
    fireEvent.click(getByRole("button"));
    expect(getByRole("button").textContent).toBe("lavender");
    act(() => {
      setTheme("mauve");
    });
    expect(getByRole("button").textContent).toBe("mauve");
  });
});
