import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";
import { Progress } from "./Progress";

afterEach(cleanup);

describe("Progress", () => {
  test("tells screen readers its value", () => {
    render(<Progress label="Learning" value={62} />);
    const bar = screen.getByRole("progressbar", { name: "Learning" });
    expect(bar.getAttribute("aria-valuenow")).toBe("62");
  });
});
