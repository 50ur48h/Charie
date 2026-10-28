import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";
import { Database } from "lucide-react";
import { IconBox } from "./IconBox";

afterEach(cleanup);

describe("IconBox", () => {
  test("uses the colors of its tone", () => {
    const { container } = render(<IconBox icon={Database} tone="good" />);
    const box = container.firstElementChild;
    expect(box?.className).toContain("bg-good-soft");
    expect(box?.className).toContain("text-good-ink");
  });

  test("is hidden from screen readers", () => {
    const { container } = render(<IconBox icon={Database} />);
    expect(container.firstElementChild?.getAttribute("aria-hidden")).toBe("true");
  });
});
