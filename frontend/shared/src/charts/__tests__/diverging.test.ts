import { describe, expect, it } from "vitest";
import { divergingOption } from "../diverging";
import { SALES_CHANGE, percentFormat } from "../../mocks";
import { light } from "./fixtures";

describe("divergingOption", () => {
  it("puts the biggest gain on top", () => {
    const option = divergingOption(SALES_CHANGE, light, percentFormat) as {
      yAxis: { data: string[] };
    };
    expect(option.yAxis.data[option.yAxis.data.length - 1]).toBe("Dallas Uptown");
  });

  it("colors highlighted bars with the theme's bad color", () => {
    const option = divergingOption(SALES_CHANGE, light, percentFormat) as {
      series: [{ data: { value: number; itemStyle: { color: unknown } }[] }];
    };
    const downtown = option.series[0].data.find((d) => d.value === -18.2);
    const dallas = option.series[0].data.find((d) => d.value === 14.8);
    expect(downtown?.itemStyle.color).toBe(light.bad);
    expect(dallas?.itemStyle.color).not.toBe(light.bad);
  });

  it("puts a long highlighted bar's label inside, in white", () => {
    const option = divergingOption(SALES_CHANGE, light, percentFormat) as {
      series: [{ data: { value: number; label: { position: string; color: string } }[] }];
    };
    const downtown = option.series[0].data.find((d) => d.value === -18.2);
    expect(downtown?.label.position).toBe("insideLeft");
    expect(downtown?.label.color).toBe("#ffffff");
  });

  it("gives the sample data an axis from −25 to 20", () => {
    const option = divergingOption(SALES_CHANGE, light, percentFormat) as {
      xAxis: { min: number; max: number };
    };
    expect(option.xAxis.min).toBe(-25);
    expect(option.xAxis.max).toBe(20);
  });

  it("shows name and label in the tooltip", () => {
    const option = divergingOption(SALES_CHANGE, light, percentFormat) as {
      tooltip: { formatter: (p: { name: string }[]) => string };
    };
    expect(option.tooltip.formatter([{ name: "Dallas Uptown" }])).toBe(
      "Dallas Uptown: +14.8%",
    );
  });
});
