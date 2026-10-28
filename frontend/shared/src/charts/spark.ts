import type { EChartsCoreOption } from "echarts/core";
import { fade, solid } from "./helpers";

export function sparkOption(values: number[], color: string): EChartsCoreOption {
  const c = solid(color);
  return {
    animationDuration: 900,
    grid: { left: 0, right: 0, top: 3, bottom: 3 },
    xAxis: {
      type: "category",
      show: false,
      boundaryGap: false,
      data: values.map((_, i) => i),
    },
    yAxis: { type: "value", show: false, scale: true },
    series: [
      {
        type: "line",
        data: values,
        smooth: 0.4,
        symbol: "none",
        lineStyle: { width: 2, color: c },
        areaStyle: { color: fade(c, 0.25) },
      },
    ],
  };
}
