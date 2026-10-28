import { describe, expect, it } from "vitest";
import { lineOption } from "../line";
import { DELIVERY_PER_DAY, thousandsFormat } from "../../mocks";
import { light } from "./fixtures";

describe("lineOption", () => {
  it("draws the second series as a dashed line", () => {
    const option = lineOption(DELIVERY_PER_DAY, light, thousandsFormat) as {
      series: [{ lineStyle: { width: number } }, { lineStyle: { width: number; type?: string } }];
    };
    expect(option.series[0].lineStyle.width).toBe(2.6);
    expect(option.series[1].lineStyle).toMatchObject({ width: 1.5, type: "dashed" });
  });

  it("shades the band only when there is one", () => {
    const withBand = lineOption(DELIVERY_PER_DAY, light, thousandsFormat) as {
      series: [{ markArea: { itemStyle: { color: string } } }];
    };
    expect(withBand.series[0].markArea.itemStyle.color).toContain("rgba");
    const withoutBandData = {
      labels: DELIVERY_PER_DAY.labels,
      series: DELIVERY_PER_DAY.series,
    };
    const withoutBand = lineOption(withoutBandData, light, thousandsFormat) as {
      series: [{ markArea?: unknown }];
    };
    expect(withoutBand.series[0].markArea).toBeUndefined();
  });

  it("shows about 6 labels along the bottom", () => {
    const option = lineOption(DELIVERY_PER_DAY, light, thousandsFormat) as {
      xAxis: { axisLabel: { interval: number } };
    };
    expect(option.xAxis.axisLabel.interval).toBe(4);
  });
});
