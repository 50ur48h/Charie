import type { EChartsCoreOption } from "echarts/core";
import type { ChartTheme } from "../theme/chartTheme";
import { fade, grad, rgba, solid, tooltipStyle } from "./helpers";
import type { ChartFormat, Series } from "./types";

export interface LineData {
  labels: string[];
  series: Series[];
  band?: { from: string; to: string; label: string };
}

export function lineOption(
  data: LineData,
  theme: ChartTheme,
  format: ChartFormat,
): EChartsCoreOption {
  const accent = solid(theme.accent);
  const tooltipFormat = format.tooltip ?? format.axis;
  const [first, second] = data.series;
  return {
    textStyle: { fontFamily: theme.font },
    animationDuration: 1200,
    grid: { left: 6, right: 14, top: 40, bottom: 4, containLabel: true },
    legend: {
      top: 0,
      left: 0,
      icon: "roundRect",
      itemWidth: 14,
      itemHeight: 4,
      itemGap: 18,
      textStyle: { color: theme.muted, fontSize: 12, fontFamily: theme.font },
    },
    tooltip: {
      ...tooltipStyle(theme),
      trigger: "axis",
      valueFormatter: (value: number | string) => tooltipFormat(Number(value)),
    },
    xAxis: {
      type: "category",
      boundaryGap: false,
      data: data.labels,
      axisLine: { lineStyle: { color: theme.grid } },
      axisTick: { show: false },
      axisLabel: {
        color: theme.muted,
        fontSize: 11,
        interval: Math.max(0, Math.ceil(data.labels.length / 6) - 1),
        alignMinLabel: "left",
        alignMaxLabel: "right",
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
    series: [
      {
        name: first.name,
        type: "line",
        data: first.values,
        smooth: 0.35,
        symbol: "circle",
        symbolSize: 7,
        showSymbol: false,
        lineStyle: { width: 2.6, color: grad(theme.accent, 1, 0) },
        itemStyle: { color: accent },
        areaStyle: { color: fade(accent, 0.2) },
        ...(data.band
          ? {
              markArea: {
                silent: true,
                itemStyle: { color: rgba(solid(theme.bad), 0.08) },
                label: {
                  color: solid(theme.bad),
                  fontSize: 11,
                  fontWeight: 600,
                  position: "insideTop",
                  distance: 8,
                  fontFamily: theme.font,
                },
                data: [
                  [{ name: data.band.label, xAxis: data.band.from }, { xAxis: data.band.to }],
                ],
              },
            }
          : {}),
      },
      ...(second
        ? [
            {
              name: second.name,
              type: "line" as const,
              data: second.values,
              smooth: 0.35,
              symbol: "none",
              lineStyle: { width: 1.5, type: "dashed" as const, color: theme.muted },
              itemStyle: { color: theme.muted },
            },
          ]
        : []),
    ],
  };
}
