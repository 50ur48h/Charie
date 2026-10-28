import { describe, expect, it } from "vitest";
import { barOption } from "../bar";
import { TOP_RESTAURANTS, thousandsFormat } from "../../mocks";
import { dark, light } from "./fixtures";

describe("barOption", () => {
  it("puts the biggest value on top", () => {
    const option = barOption(TOP_RESTAURANTS, light, thousandsFormat) as {
      yAxis: { data: string[] };
      xAxis: { max: number; axisLabel: { showMaxLabel: boolean } };
    };
    expect(option.yAxis.data[option.yAxis.data.length - 1]).toBe("Downtown Austin");
    expect(option.xAxis.max).toBeGreaterThan(96200);
    expect(option.xAxis.axisLabel.showMaxLabel).toBe(false);
  });

  it("colors highlighted bars with the accent color", () => {
    const option = barOption(TOP_RESTAURANTS, light, thousandsFormat) as {
      series: [{ data: { value: number; itemStyle: { color: unknown } }[] }];
    };
    const downtown = option.series[0].data.find((d) => d.value === 96200);
    const dallas = option.series[0].data.find((d) => d.value === 88400);
    expect(downtown?.itemStyle.color).toBe(light.accent);
    expect(dallas?.itemStyle.color).not.toBe(light.accent);
  });

  it("themes the grid for light and dark", () => {
    const lightOption = barOption(TOP_RESTAURANTS, light, thousandsFormat) as {
      xAxis: { splitLine: { lineStyle: { color: string } } };
    };
    const darkOption = barOption(TOP_RESTAURANTS, dark, thousandsFormat) as {
      xAxis: { splitLine: { lineStyle: { color: string } } };
    };
    expect(lightOption.xAxis.splitLine.lineStyle.color).not.toBe(
      darkOption.xAxis.splitLine.lineStyle.color,
    );
  });
});
