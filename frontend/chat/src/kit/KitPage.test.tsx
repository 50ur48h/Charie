import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";
import KitPage from "./KitPage";

afterEach(() => {
  cleanup();
  localStorage.clear();
  delete document.documentElement.dataset.theme;
});

describe("KitPage", () => {
  test("shows the 6 theme buttons", () => {
    render(<KitPage />);
    for (const name of ["Sage", "Lavender", "Mist", "Seafoam", "Mauve", "Slate"]) {
      expect(screen.getByRole("button", { name })).toBeTruthy();
    }
  });

  test("clicking Lavender switches the theme", () => {
    render(<KitPage />);
    fireEvent.click(screen.getByRole("button", { name: "Lavender" }));
    expect(document.documentElement.dataset.theme).toBe("lavender");
    expect(localStorage.getItem("charie-theme")).toBe("lavender");
  });
});
