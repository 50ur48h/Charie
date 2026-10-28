import type { EChartsCoreOption } from "echarts/core";
import type { ChartTheme } from "../theme/chartTheme";
import { grad, niceStep, rgba, solid, tooltipStyle } from "./helpers";
import type { ChartFormat, ChartItem } from "./types";

export interface BarData {
  items: ChartItem[];
  highlight?: string[];
}

export function barOption(data: BarData, theme: ChartTheme, format: ChartFormat): EChartsCoreOption {
  const items = data.items.slice().sort((a, b) => a.value - b.value);
  const values = items.map((i) => i.value);
  const longest = values.reduce((m, v) => Math.max(m, v), 0);
  const step = longest > 0 ? niceStep(longest / 4) : 1;
  const max = longest > 0 ? Math.ceil((longest + 0.8 * step) / step) * step : 1;
  const r = theme.barRadius;
  const tooltipFormat = format.tooltip ?? format.axis;
  return {
    textStyle: { fontFamily: theme.font },
    animationDuration: 900,
    animationEasing: "cubicOut",
    grid: { left: 6, right: 56, top: 6, bottom: 6, containLabel: true },
    tooltip: {
      ...tooltipStyle(theme),
      trigger: "axis",
      axisPointer: { type: "shadow", shadowStyle: { color: rgba(theme.muted, 0.07) } },
      valueFormatter: (value: number | string) => tooltipFormat(Number(value)),
    },
    xAxis: {
      type: "value",
      min: 0,
      max,
      axisLabel: {
        color: theme.muted,
        fontSize: 11,
        showMinLabel: false,
        showMaxLabel: false,
        formatter: (v: number) => format.axis(v),
      },
      splitLine: { lineStyle: { color: theme.grid, type: theme.gridType } },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    yAxis: {
      type: "category",
      data: items.map((i) => i.name),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: theme.text,
        fontSize: 12,
        margin: 14,
        formatter: (v: string) =>
          data.highlight?.includes(v) ? `{hl|${v}}` : v,
        rich: {
          hl: { color: solid(theme.accentInk), fontWeight: 700, fontSize: 12, fontFamily: theme.font },
        },
      },
    },
    series: [
      {
        type: "bar",
        barWidth: theme.barWidth,
        data: items.map((item) => {
          const hl = data.highlight?.includes(item.name) ?? false;
          const color = hl ? theme.accent : theme.pos;
          const inside = hl && longest > 0 && item.value >= longest * 0.5;
          return {
            value: item.value,
            itemStyle: { color: grad(color, 1, 0), borderRadius: [0, r, r, 0] },
            label: {
              show: true,
              position: inside ? "insideRight" : "right",
              distance: inside ? 8 : 6,
              formatter: item.label,
              color: inside ? "#ffffff" : hl ? solid(theme.accentInk) : theme.muted,
              fontWeight: hl ? 700 : 500,
              fontSize: 11.5,
              fontFamily: theme.font,
            },
          };
        }),
        animationDelay: (i: number) => i * 45,
      },
    ],
  };
}
