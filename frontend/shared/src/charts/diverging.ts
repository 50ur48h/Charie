import type { EChartsCoreOption } from "echarts/core";
import type { ChartTheme } from "../theme/chartTheme";
import { escHtml, grad, niceStep, rgba, solid, tooltipStyle } from "./helpers";
import type { ChartFormat, ChartItem } from "./types";

export interface DivergingData {
  items: ChartItem[];
  highlight?: string[];
}

export function divergingOption(
  data: DivergingData,
  theme: ChartTheme,
  format: ChartFormat,
  preserveOrder = false,
): EChartsCoreOption {
  // Kit demos sort by value; answer charts pass preserveOrder to keep
  // the server category order instead.
  const items = preserveOrder
    ? data.items.slice()
    : data.items.slice().sort((a, b) => a.value - b.value);
  const values = items.map((i) => i.value);
  const maxAbs = values.length ? Math.max(...values.map((v) => Math.abs(v))) : 0;
  const step = maxAbs > 0 ? niceStep(maxAbs / 4) : 1;
  const lo = values.length ? Math.min(...values) : 0;
  const hi = values.length ? Math.max(...values) : 0;
  const min = maxAbs > 0 ? Math.floor((lo - 1.2 * step) / step) * step : -1;
  const max = maxAbs > 0 ? Math.ceil((hi + 0.8 * step) / step) * step : 1;
  const r = theme.barRadius;
  return {
    textStyle: { fontFamily: theme.font },
    animationDuration: 900,
    animationEasing: "cubicOut",
    grid: { left: 6, right: 56, top: 6, bottom: 6, containLabel: true },
    tooltip: {
      ...tooltipStyle(theme),
      trigger: "axis",
      axisPointer: { type: "shadow", shadowStyle: { color: rgba(theme.muted, 0.07) } },
      formatter: (params: { name: string } | { name: string }[]) => {
        const p = Array.isArray(params) ? params[0] : params;
        const item = items.find((i) => i.name === p.name);
        return `${escHtml(p.name)}: ${item ? escHtml(item.label) : ""}`;
      },
    },
    xAxis: {
      type: "value",
      min,
      max,
      axisLabel: {
        color: theme.muted,
        fontSize: 11,
        showMinLabel: false,
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
          hl: { color: solid(theme.badInk), fontWeight: 700, fontSize: 12, fontFamily: theme.font },
        },
      },
    },
    series: [
      {
        type: "bar",
        barWidth: theme.barWidth,
        data: items.map((item) => {
          const up = item.value >= 0;
          const hl = data.highlight?.includes(item.name) ?? false;
          const color = hl ? theme.badInk : up ? theme.pos : theme.neg;
          const inside = hl && maxAbs > 0 && Math.abs(item.value) >= maxAbs * 0.5;
          return {
            value: item.value,
            itemStyle: {
              color: grad(color, 1, 0, !up),
              borderRadius: up ? [0, r, r, 0] : [r, 0, 0, r],
            },
            label: {
              show: true,
              position: inside ? (up ? "insideRight" : "insideLeft") : up ? "right" : "left",
              distance: inside ? 8 : 6,
              formatter: item.label,
              color: inside ? "#ffffff" : hl ? solid(theme.badInk) : theme.muted,
              fontWeight: hl ? 700 : 500,
              fontSize: 11.5,
              fontFamily: theme.font,
            },
          };
        }),
        markLine: {
          silent: true,
          symbol: "none",
          label: { show: false },
          lineStyle: { color: theme.text, opacity: 0.22, type: "solid", width: 1 },
          data: [{ xAxis: 0 }],
        },
        animationDelay: (i: number) => i * 45,
      },
    ],
  };
}
