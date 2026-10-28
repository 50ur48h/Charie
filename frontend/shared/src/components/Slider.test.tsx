import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";
import { Slider } from "./Slider";

afterEach(cleanup);

describe("Slider", () => {
  test("the arrow keys change the value by one step", () => {
    render(<Slider aria-label="10 minutes" defaultValue={10} min={2} max={15} step={1} />);
    const thumb = screen.getByRole("slider", { name: "10 minutes" });
    expect(thumb.getAttribute("aria-valuenow")).toBe("10");
    fireEvent.keyDown(thumb, { key: "ArrowRight" });
    expect(thumb.getAttribute("aria-valuenow")).toBe("11");
    fireEvent.keyDown(thumb, { key: "ArrowLeft" });
    fireEvent.keyDown(thumb, { key: "ArrowLeft" });
    expect(thumb.getAttribute("aria-valuenow")).toBe("9");
  });
});
