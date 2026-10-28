// Answer chart blocks (architecture 09) mapped onto the P02 chart kit.
// Plot v, label f: every business number on screen is the backend's own
// formatted string. Server category order is preserved (the kit's value
// sorts stay opt-in for kit demos). Missing values stay missing (null y
// is a gap in lines and stacks, a dropped row in bars — never a plotted
// zero). Axis ticks are scaffolding only (compact per unit) until
// format.ts arrives with P05.6; tooltips show the supplied f by point
// index, never by value lookup.
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
  key: string;
  x: string;
  v: number | null;
  f: string;
}

function cellText(cell: Exclude<Cell, null | undefined>): { key: string; text: string } {
  if (typeof cell === "object") return { key: String(cell.v), text: cell.f };
  return { key: String(cell), text: String(cell) };
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
    const { key, text } = cellText(xRaw);
    const yRaw: Cell = row[yIndex];
    if (yRaw === null || yRaw === undefined) {
      points.push({ key, x: text, v: null, f: "" });
    } else if (typeof yRaw === "object") {
      points.push({ key, x: text, v: yRaw.v, f: yRaw.f });
    } else if (typeof yRaw === "number") {
      points.push({ key, x: text, v: yRaw, f: String(yRaw) });
    } else {
      points.push({ key, x: text, v: null, f: yRaw });
    }
  }
  return points;
}

// Trimmed decimals that keep distinct small ticks distinguishable:
// percent matches the backend's one-decimal labels, ratios keep three.
function trimDecimals(v: number, places: number): string {
  return String(parseFloat(v.toFixed(places)));
}

// Compact axis scaffolding per unit. Tooltips never use this: they show
// the backend's f through the index lookup below.
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
  if (unit === "percent") return (v) => `${trimDecimals(v, 1)}%`;
  if (unit === "ratio") return (v) => trimDecimals(v, 3);
  return (v) => fmtNum(v);
}

function lookupFormat(
  shown: { v: number | null; f: string }[],
  axis: (v: number) => string,
): ChartFormat {
  const byValue = new Map<number, string>();
  for (const point of shown) {
    if (point.v !== null && !byValue.has(point.v)) byValue.set(point.v, point.f);
  }
  return {
    axis,
    tooltip: (v) => byValue.get(v) ?? axis(v),
    tooltipByIndex: (index) => {
      const point = shown[index];
      if (point === undefined) return undefined;
      if (point.v === null) return "No data";
      return point.f;
    },
  };
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

/** Map an answer chart block onto a kit option. Null when the kind is unknown. */
export function buildChartOption(
  block: ChartBlock,
  theme: ChartTheme,
): ChartFigure | null {
  const points = pointsOf(block);
  const axis = axisFormat(block.unit, block.currency);
  const height = CHART_HEIGHTS[block.kind] ?? 300;
  const highlighted = (point: Point): boolean =>
    block.highlight?.includes(point.x) === true ||
    block.highlight?.includes(point.key) === true;
  switch (block.kind) {
    case "bar":
    case "bar_diverging": {
      const shown = points.filter((p) => p.v !== null);
      const format = lookupFormat(shown, axis);
      const data = {
        items: shown.map((p) => ({ name: p.x, value: p.v as number, label: p.f })),
        highlight: shown.filter(highlighted).map((p) => p.x),
      };
      const option =
        block.kind === "bar"
          ? barOption(data, theme, format, true)
          : divergingOption(data, theme, format, true);
      return { height, option: narrowTicks(option) };
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
          lookupFormat(points, axis),
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
          lookupFormat(points, axis),
        ),
      };
    default:
      return null;
  }
}

/** Plain-text data summary for screen readers: "Downtown: −18.2%; …". */
export function chartSummary(block: ChartBlock): string {
  return pointsOf(block)
    .filter((p) => p.f !== "")
    .map((p) => `${p.x}: ${p.f}`)
    .join("; ");
}
