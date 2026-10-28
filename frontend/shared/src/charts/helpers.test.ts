import { describe, expect, test } from "vitest";
import { escHtml, mix, niceStep, rgba } from "./helpers";

describe("helpers", () => {
  test("rgba turns a hex color into rgba", () => {
    expect(rgba("#6E9277", 0.2)).toBe("rgba(110, 146, 119, 0.2)");
  });

  test("mix blends two colors", () => {
    expect(mix("#ffffff", "#000000", 0.1)).toBe("rgb(230, 230, 230)");
    expect(mix("#000000", "#ffffff", 1)).toBe("rgb(255, 255, 255)");
  });

  test("escHtml neutralizes markup", () => {
    expect(escHtml('<img src="x" onerror="alert(1)">')).toBe(
      "&lt;img src=&quot;x&quot; onerror=&quot;alert(1)&quot;&gt;",
    );
    expect(escHtml("fish & chips")).toBe("fish &amp; chips");
  });

  test("niceStep picks 1, 2, 2.5 or 5 times a power of ten", () => {
    expect(niceStep(3)).toBe(5);
    expect(niceStep(5)).toBe(5);
    expect(niceStep(6)).toBe(10);
    expect(niceStep(0.3)).toBe(0.5);
    expect(niceStep(400)).toBe(500);
  });
});
