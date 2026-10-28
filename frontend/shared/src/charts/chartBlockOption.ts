// Answer chart blocks (architecture 09) mapped onto the P02 chart kit.
// Plot v, label f: every business number on screen is the backend's own
// formatted string. Missing values stay missing (null y is a gap in lines
// and stacks, a dropped row in bars — never a plotted zero). Rows pass
// through in server order; the kit's bar sorts are kit design. Axis ticks
// are scaffolding only (compact per unit) until format.ts arrives with
// P05.6; tooltips show the supplied f via a value lookup.
import type { EChartsCoreOption } from "echarts/core";
import type { ChartTheme } from "../theme/chartTheme";
import { barOption } from "./bar";
import { divergingOption } from "./diverging";
import { lineOption } from "./line";
import { stackedBarsOption } from "./stackedBars";
import { fmtNum, type ChartFormat } from "./types";
import type { Cell, ChartBlock } from "../api/chat-types";

export const CHART_HEIGHTS: Record<string, number> = {
  bar: 260,
  bar_diverging: 360,
  line: 280,
  bar_stacked: 300,
};

interface Point {
  x: string;
  v: number | null;
  f: string;
}

function pointsOf(block: ChartBlock): Point[] {
  // Rows are positional: columns names the slots, x and y pick them.
  const xIndex = block.data.columns.indexOf(block.x);
  const yIndex = block.data.columns.indexOf(block.y);
  const points: Point[] = [];
  if (xIndex === -1 || yIndex === -1) return points;
  for (const row of block.data.rows) {
    const xRaw = row[xIndex];
    if (xRaw === null || xRaw === undefined) continue;
    const x = typeof xRaw === "string" ? xRaw : String(xRaw);
    const yRaw: Cell = row[yIndex];
    if (yRaw === null || yRaw === undefined) {
      points.push({ x, v: null, f: "" });
    } else if (typeof yRaw === "object") {
      points.push({ x, v: yRaw.v, f: yRaw.f });
    } else if (typeof yRaw === "number") {
      points.push({ x, v: yRaw, f: String(yRaw) });
    } else {
      points.push({ x, v: null, f: yRaw });
    }
  }
  return points;
}

// Compact axis scaffolding per unit. Tooltips never use this: they show
// the backend's f through the lookup below.
function axisFormat(unit: string, currency?: string): (v: number) => string {
  if (unit === "money") {
    if (currency === undefined) return (v) => fmtNum(v);
    try {
      const fmt = new Intl.NumberFormat("en", {
        style: "currency",
        currency,
        notation: "compact",
        maximumFractionDigits: 1,
      });
      return (v) => fmt.format(v);
    } catch {
      return (v) => fmtNum(v);
    }
  }
  if (unit === "percent") return (v) => `${Math.round(v)}%`;
  if (unit === "ratio") return (v) => `${Math.round(v * 100) / 100}`;
  return (v) => fmtNum(v);
}

function lookupFormat(points: Point[], axis: (v: number) => string): ChartFormat {
  const byValue = new Map<number, string>();
  for (const point of points) {
    if (point.v !== null && !byValue.has(point.v)) byValue.set(point.v, point.f);
  }
  return { axis, tooltip: (v) => byValue.get(v) ?? axis(v) };
}

// B002: the design's fixed axis config crowds value-axis ticks on phones.
// Answer bars keep the kit option untouched and add a narrow-screen media
// rule, so laptop rendering is byte-identical to the design.
function narrowTicks(option: EChartsCoreOption): EChartsCoreOption {
  return {
    ...option,
    media: [
      { query: { maxWidth: 480 }, option: { xAxis: { splitNumber: 2 } } },
      ...(Array.isArray(option.media) ? option.media : []),
    ],
  };
}

export interface ChartFigure {
  height: number;
  option: EChartsCoreOption;
}

/** Plain-text data summary for screen readers: "Downtown: −18.2%; …". */
export function chartSummary(block: ChartBlock): string {
  return pointsOf(block)
    .filter((p) => p.f !== "")
    .map((p) => `${p.x}: ${p.f}`)
    .join("; ");
}

/** Map an answer chart block onto a kit option. Null when the kind is unknown. */
export function buildChartOption(
  block: ChartBlock,
  theme: ChartTheme,
): ChartFigure | null {
  const points = pointsOf(block);
  const axis = axisFormat(block.unit, block.currency);
  const format = lookupFormat(points, axis);
  const height = CHART_HEIGHTS[block.kind] ?? 300;
  switch (block.kind) {
    case "bar": {
      const items = points
        .filter((p) => p.v !== null)
        .map((p) => ({ name: p.x, value: p.v as number, label: p.f }));
      return {
        height,
        option: narrowTicks(barOption({ items, highlight: block.highlight }, theme, format)),
      };
    }
    case "bar_diverging": {
      const items = points
        .filter((p) => p.v !== null)
        .map((p) => ({ name: p.x, value: p.v as number, label: p.f }));
      return {
        height,
        option: narrowTicks(
          divergingOption({ items, highlight: block.highlight }, theme, format),
        ),
      };
    }
    case "line":
      return {
        height,
        option: lineOption(
          {
            labels: points.map((p) => p.x),
            series: [{ name: block.y, values: points.map((p) => p.v) }],
          },
          theme,
          format,
        ),
      };
    case "bar_stacked":
      // The 09 contract carries one y column, so a stacked block arrives
      // as a single series. Render it whole rather than inventing splits.
      return {
        height,
        option: stackedBarsOption(
          {
            labels: points.map((p) => p.x),
            series: [{ name: block.y, values: points.map((p) => p.v) }],
          },
          theme,
          format,
        ),
      };
    default:
      return null;
  }
}
