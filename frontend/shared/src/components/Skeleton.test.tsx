import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";
import { Skeleton } from "./Skeleton";

afterEach(cleanup);

describe("Skeleton", () => {
  test("is hidden from screen readers", () => {
    const { container } = render(<Skeleton className="h-3 w-2/5" />);
    const skeleton = container.firstElementChild;
    expect(skeleton?.getAttribute("aria-hidden")).toBe("true");
  });
});
