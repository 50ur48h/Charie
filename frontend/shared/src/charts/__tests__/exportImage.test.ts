import { describe, expect, it } from "vitest";
import { chartFileName } from "../exportImage";

describe("chartFileName", () => {
  it("turns the title into a file name", () => {
    expect(chartFileName("Sales change by restaurant")).toBe(
      "sales-change-by-restaurant.png",
    );
  });

  it("falls back to chart.png", () => {
    expect(chartFileName("")).toBe("chart.png");
  });
});
