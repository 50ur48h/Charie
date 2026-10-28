import { describe, expect, it } from "vitest";
import { countFormat, dollarFormat, percentFormat, thousandsFormat } from "./sampleCharts";

describe("sample formats", () => {
  it("percent formats axis whole and tooltip with one decimal", () => {
    expect(percentFormat.axis(10)).toBe("+10%");
    expect(percentFormat.axis(-20)).toBe("−20%");
    expect(percentFormat.tooltip?.(14.8)).toBe("+14.8%");
  });

  it("thousands formats compact dollars", () => {
    expect(thousandsFormat.axis(96200)).toBe("$96.2K");
  });

  it("dollar formats whole dollars and cents", () => {
    expect(dollarFormat.axis(2)).toBe("$2");
    expect(dollarFormat.tooltip?.(1.22)).toBe("$1.22");
  });

  it("count formats plain numbers, never dollars", () => {
    expect(countFormat.axis(300)).toBe("300");
    expect(countFormat.tooltip?.(224)).toBe("224");
    expect(countFormat.axis(1500)).not.toContain("$");
  });
});
