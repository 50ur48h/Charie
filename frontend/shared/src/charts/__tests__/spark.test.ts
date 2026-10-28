import { describe, expect, it } from "vitest";
import { sparkOption } from "../spark";
import { light } from "./fixtures";
import { solid } from "../helpers";

describe("sparkOption", () => {
  it("keeps only a smooth line with area fill", () => {
    const option = sparkOption([1, 2, 3, 4], light.accent) as {
      xAxis: { show: boolean };
      yAxis: { show: boolean };
      series: [{ smooth: unknown; symbol: string; lineStyle: { color: string } }];
    };
    expect(option.xAxis.show).toBe(false);
    expect(option.yAxis.show).toBe(false);
    expect(option.series[0]).toMatchObject({ smooth: 0.4, symbol: "none" });
    expect(option.series[0].lineStyle.color).toBe(solid(light.accent));
  });
});
