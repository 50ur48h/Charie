import type { EChartsCoreOption } from "echarts/core";
import type { ChartTheme } from "../theme/chartTheme";
import { rgba, solid, tooltipStyle } from "./helpers";
import type { ChartFormat, Series } from "./types";

export interface StackedData {
  labels: string[];
  series: Series[];
  labelEvery?: number;
}

export function stackedBarsOption(
  data: StackedData,
  theme: ChartTheme,
  format: ChartFormat,
): EChartsCoreOption {
  const r = theme.barRadius;
  const colors = [solid(theme.pos), solid(theme.accent)];
  const tooltipFormat = format.tooltip ?? format.axis;
  return {
    textStyle: { fontFamily: theme.font },
    animationDuration: 900,
    grid: { left: 6, right: 8, top: 40, bottom: 4, containLabel: true },
    legend: {
      top: 0,
      left: 0,
      icon: "roundRect",
      itemWidth: 12,
      itemHeight: 8,
      itemGap: 18,
      textStyle: { color: theme.muted, fontSize: 12, fontFamily: theme.font },
    },
    tooltip: {
      ...tooltipStyle(theme),
      trigger: "axis",
      axisPointer: { type: "shadow", shadowStyle: { color: rgba(theme.muted, 0.07) } },
      valueFormatter: (value: number | string) => tooltipFormat(Number(value)),
    },
    xAxis: {
      type: "category",
      data: data.labels,
      axisLine: { lineStyle: { color: theme.grid } },
      axisTick: { show: false },
      axisLabel: {
        color: theme.muted,
        fontSize: 11,
        interval: data.labelEvery ?? "auto",
      },
    },
    yAxis: {
      type: "value",
      splitNumber: 4,
      axisLabel: {
        color: theme.muted,
        fontSize: 11,
        formatter: (v: number) => format.axis(v),
      },
      splitLine: { lineStyle: { color: theme.grid, type: theme.gridType } },
    },
    series: data.series.map((s, i) => ({
      name: s.name,
      type: "bar" as const,
      stack: "total",
      barWidth: "58%",
      data: s.values,
      itemStyle: {
        color: colors[i % 2],
        borderRadius: i === data.series.length - 1 ? [r, r, 0, 0] : 0,
      },
      animationDelay: (idx: number) => idx * 18,
    })),
  };
}
