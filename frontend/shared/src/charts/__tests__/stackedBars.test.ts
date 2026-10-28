import { describe, expect, it } from "vitest";
import { stackedBarsOption } from "../stackedBars";
import { COST_PER_DAY, dollarFormat } from "../../mocks";
import { light } from "./fixtures";

describe("stackedBarsOption", () => {
  it("stacks the series", () => {
    const option = stackedBarsOption(COST_PER_DAY, light, dollarFormat) as {
      series: { stack: string; name: string }[];
    };
    expect(option.series.map((s) => s.name)).toEqual(["Learning", "Questions"]);
    expect(option.series.every((s) => s.stack === "total")).toBe(true);
  });

  it("rounds only the top layer", () => {
    const option = stackedBarsOption(COST_PER_DAY, light, dollarFormat) as {
      series: { itemStyle: { borderRadius: unknown } }[];
    };
    expect(option.series[0].itemStyle.borderRadius).toBe(0);
    expect(option.series[option.series.length - 1].itemStyle.borderRadius).toEqual([6, 6, 0, 0]);
  });

  it("shows every 4th label when labelEvery is 4", () => {
    const option = stackedBarsOption(COST_PER_DAY, light, dollarFormat) as {
      xAxis: { axisLabel: { interval: number | string } };
    };
    expect(option.xAxis.axisLabel.interval).toBe(4);
  });
});
