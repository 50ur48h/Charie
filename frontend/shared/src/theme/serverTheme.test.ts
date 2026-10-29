import { afterEach, describe, expect, test } from "vitest";
import { applyServerTheme } from "./serverTheme";
import { DEFAULT_THEME, getTheme, THEME_STORAGE_KEY } from "./theme";

afterEach(() => {
  localStorage.clear();
  delete document.documentElement.dataset.theme;
});

describe("applyServerTheme", () => {
  test("the server theme replaces a different browser theme", () => {
    document.documentElement.dataset.theme = "sage";
    localStorage.setItem(THEME_STORAGE_KEY, "sage");
    applyServerTheme("lavender");
    expect(document.documentElement.dataset.theme).toBe("lavender");
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("lavender");
  });

  test("it keeps the browser theme when nothing changed", () => {
    document.documentElement.dataset.theme = "mist";
    localStorage.setItem(THEME_STORAGE_KEY, "mist");
    applyServerTheme("mist");
    expect(document.documentElement.dataset.theme).toBe("mist");
  });

  test("an unknown server theme falls back to sage", () => {
    applyServerTheme("ocean");
    expect(getTheme()).toBe(DEFAULT_THEME);
  });

  test("an unknown server theme keeps the browser theme", () => {
    document.documentElement.dataset.theme = "mist";
    localStorage.setItem(THEME_STORAGE_KEY, "mist");
    applyServerTheme("ocean");
    expect(document.documentElement.dataset.theme).toBe("mist");
  });
});
