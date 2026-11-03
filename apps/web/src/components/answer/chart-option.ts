/**
 * The answer's chart, translated from the server's Vega-Lite spec into the
 * Calm design's ECharts figures.
 *
 * The server assembles the spec from a closed vocabulary (`agent/charts.py`):
 * a mark from `bar | line | point | area`, x / y / optional colour encodings,
 * and inline values — never a URL. This module reads exactly that vocabulary
 * and nothing more, so a spec it does not understand yields `null` (and the
 * figure says so) rather than a picture that misrepresents the data.
 *
 * The styling follows the approved design: soft diverging bars when values go
 * both ways, a smooth line with a fading area for a series over time, dashed
 * hairline grids, muted 11px axis labels, and tooltips on the card surface.
 */

export interface ChartTheme {
  font: string;
  text: string;
  muted: string;
  grid: string;
  accent: string;
  pos: string;
  neg: string;
  bad: string;
  good: string;
  surface: string;
  border: string;
  categories: string[];
}

const FALLBACK_CATEGORIES = [
  "#6e9277",
  "#c9a15a",
  "#7fa7c9",
  "#c98b8b",
  "#9c8cc4",
  "#6fafa5",
  "#b0a46e",
  "#9a9a9a",
];

/** The chart colours of whatever palette and mode the page is in right now. */
export function readChartTheme(): ChartTheme {
  const styles =
    typeof window === "undefined" ? null : window.getComputedStyle(document.documentElement);
  const read = (name: string, fallback: string): string =>
    styles?.getPropertyValue(name).trim() || fallback;
  return {
    font: "'Inter Variable', Inter, 'Segoe UI', system-ui, sans-serif",
    text: read("--text", "#232a22"),
    muted: read("--chart-muted", "#7a8477"),
    grid: read("--chart-grid", "#e2e7dd"),
    accent: read("--accent", "#6e9277"),
    pos: read("--chart-pos", "#b5cdb9"),
    neg: read("--chart-neg", "#ebc2bb"),
    bad: read("--bad", "#c2554a"),
    good: read("--good", "#4e8a5e"),
    surface: read("--surface", "#fcfdfb"),
    border: read("--border", "#dfe5da"),
    categories: FALLBACK_CATEGORIES.map((fallback, index) =>
      read(`--chart-cat-${index + 1}`, fallback),
    ),
  };
}

type Kind = "quantitative" | "temporal" | "nominal" | "ordinal";

interface Channel {
  field: string;
  type: Kind;
  title: string;
  timeUnit?: string;
}

export interface BuiltChart {
  option: Record<string, unknown>;
  title: string;
  subtitle: string | null;
  height: number;
}

type Row = Record<string, unknown>;

/** `order_month` → "Order month". The server titles axes; this is the fallback. */
export function humanize(field: string): string {
  const words = field.replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim();
  return words.length === 0 ? field : words[0]!.toUpperCase() + words.slice(1);
}

function channel(raw: unknown): Channel | null {
  if (!raw || typeof raw !== "object") return null;
  const record = raw as Record<string, unknown>;
  if (typeof record.field !== "string" || record.field.length === 0) return null;
  const type: Kind =
    record.type === "quantitative" ||
    record.type === "temporal" ||
    record.type === "ordinal" ||
    record.type === "nominal"
      ? record.type
      : "nominal";
  const title =
    typeof record.title === "string" && record.title.length > 0
      ? record.title
      : humanize(record.field);
  return {
    field: record.field,
    type,
    title,
    ...(typeof record.timeUnit === "string" ? { timeUnit: record.timeUnit } : {}),
  };
}

function markOf(raw: unknown): string | null {
  if (typeof raw === "string") return raw;
  if (raw && typeof raw === "object" && typeof (raw as { type?: unknown }).type === "string") {
    return (raw as { type: string }).type;
  }
  return null;
}

function toNumber(value: unknown): number | null {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value.replace(/,/g, ""));
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function toDate(value: unknown): Date | null {
  if (value instanceof Date) return value;
  if (typeof value === "number") return new Date(value);
  if (typeof value !== "string") return null;
  // A bare date is a calendar day, not midnight UTC in somebody else's zone.
  const day = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (day) return new Date(Number(day[1]), Number(day[2]) - 1, Number(day[3]));
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

type Grain = "year" | "month" | "day" | "time";

function grainOf(axis: Channel, dates: Date[]): Grain {
  const unit = axis.timeUnit ?? "";
  if (unit === "year") return "year";
  if (unit === "yearmonth") return "month";
  if (unit === "yearmonthdate") return "day";
  if (dates.every((date) => date.getMonth() === 0 && date.getDate() === 1)) return "year";
  if (dates.every((date) => date.getDate() === 1 && date.getHours() === 0)) return "month";
  if (dates.every((date) => date.getHours() === 0 && date.getMinutes() === 0)) return "day";
  return "time";
}

function formatDate(date: Date, grain: Grain, spansYears: boolean): string {
  const month = MONTHS[date.getMonth()] ?? "";
  if (grain === "year") return String(date.getFullYear());
  if (grain === "month") return `${month} ${date.getFullYear()}`;
  if (grain === "day") {
    return spansYears ? `${date.getDate()} ${month} ${date.getFullYear()}` : `${date.getDate()} ${month}`;
  }
  const time = `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
  return `${date.getDate()} ${month} ${time}`;
}

const compactFormat = new Intl.NumberFormat("en-US", {
  notation: "compact",
  maximumFractionDigits: 1,
});

/** Labels and tooltips: every digit a reader would check. */
export function fullNumber(value: number): string {
  const digits = Math.abs(value) >= 100 || Number.isInteger(value) ? 0 : 2;
  return value.toLocaleString("en-US", { maximumFractionDigits: digits });
}

/** Axis ticks: short. 12,400 → 12.4K. */
export function compact(value: number): string {
  return Math.abs(value) >= 1000 ? compactFormat.format(value) : fullNumber(value);
}

/** How values read: "RM 28,204", "−16.6%". Units come from `usermeta` when the spec carries them. */
interface Format {
  full: (value: number) => string;
  short: (value: number) => string;
}

function formatFor(spec: Record<string, unknown>): Format {
  const meta = (spec.usermeta ?? {}) as { prefix?: unknown; suffix?: unknown };
  const prefix = typeof meta.prefix === "string" ? meta.prefix : "";
  const suffix = typeof meta.suffix === "string" ? meta.suffix : "";
  const sign = (value: number) => (value < 0 ? "−" : "");
  return {
    full: (value) => `${sign(value)}${prefix}${fullNumber(Math.abs(value))}${suffix}`,
    short: (value) => `${sign(value)}${prefix}${compact(Math.abs(value))}${suffix}`,
  };
}
function rgba(color: string, alpha: number): string {
  const hex = color.trim().replace("#", "");
  if (/^[0-9a-f]{6}$/i.test(hex)) {
    const n = parseInt(hex, 16);
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
  }
  const rgb = /rgba?\(([^)]+)\)/.exec(color);
  if (rgb) {
    const [r, g, b] = rgb[1]!.split(",").map((part) => part.trim());
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }
  return color;
}

function fade(color: string, from: number): Record<string, unknown> {
  return {
    type: "linear",
    x: 0,
    y: 0,
    x2: 0,
    y2: 1,
    colorStops: [
      { offset: 0, color: rgba(color, from) },
      { offset: 1, color: rgba(color, 0) },
    ],
  };
}

function tooltip(theme: ChartTheme, extra: Record<string, unknown>): Record<string, unknown> {
  return {
    backgroundColor: theme.surface,
    borderColor: theme.border,
    borderWidth: 1,
    padding: [8, 12],
    textStyle: { color: theme.text, fontFamily: theme.font, fontSize: 12 },
    extraCssText: "border-radius:10px;box-shadow:0 10px 30px rgba(15,20,30,.10);",
    ...extra,
  };
}

function grid(top: number, right = 16): Record<string, unknown> {
  return {
    left: 6,
    right,
    top,
    bottom: 6,
    outerBoundsMode: "same",
    outerBoundsContain: "axisLabel",
  };
}

function valueAxis(theme: ChartTheme, format: Format, extra: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    type: "value",
    splitNumber: 4,
    axisLabel: {
      color: theme.muted,
      fontSize: 11,
      fontFamily: theme.font,
      formatter: (v: number) => format.short(v),
    },
    splitLine: { lineStyle: { color: theme.grid, type: "dashed" } },
    axisLine: { show: false },
    axisTick: { show: false },
    ...extra,
  };
}

function categoryAxis(
  theme: ChartTheme,
  labels: string[],
  extra: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    type: "category",
    data: labels,
    axisLine: { lineStyle: { color: theme.grid } },
    axisTick: { show: false },
    axisLabel: { color: theme.muted, fontSize: 11, fontFamily: theme.font, hideOverlap: true },
    ...extra,
  };
}

function legend(theme: ChartTheme): Record<string, unknown> {
  return {
    top: 0,
    left: 0,
    icon: "roundRect",
    itemWidth: 14,
    itemHeight: 4,
    itemGap: 18,
    textStyle: { color: theme.muted, fontSize: 12, fontFamily: theme.font },
  };
}

interface Item {
  name: string;
  value: number;
}

/** Horizontal bars that go left (fell) or right (grew); the biggest faller is called out. */
function diverging(items: Item[], theme: ChartTheme, valueTitle: string, format: Format, narrow: boolean): Record<string, unknown> {
  const sorted = [...items].sort((a, b) => a.value - b.value);
  const lowest = sorted[0];
  const highlight = lowest && lowest.value < 0 ? lowest.name : null;
  const maxAbs = Math.max(...sorted.map((item) => Math.abs(item.value)), 1);
  const radius = 6;
  return {
    textStyle: { fontFamily: theme.font },
    animationDuration: 900,
    animationEasing: "cubicOut",
    grid: grid(6, narrow ? 44 : 56),
    tooltip: tooltip(theme, {
      trigger: "axis",
      axisPointer: { type: "shadow", shadowStyle: { color: rgba(theme.muted, 0.07) } },
      valueFormatter: (v: number) => format.full(v),
    }),
    xAxis: valueAxis(theme, format, {
      // Room beyond each end in proportion to the whole range, so a short bar's
      // label never runs into the names (the design pads both ends the same way).
      min: (extent: { min: number; max: number }) =>
        Math.min(0, extent.min) - Math.max(Math.abs(extent.min), Math.abs(extent.max), 1) * 0.24,
      max: (extent: { min: number; max: number }) =>
        Math.max(0, extent.max) + Math.max(Math.abs(extent.min), Math.abs(extent.max), 1) * 0.16,
      axisLabel: {
        color: theme.muted,
        fontSize: 11,
        fontFamily: theme.font,
        showMinLabel: false,
        showMaxLabel: false,
        formatter: (v: number) => `${v > 0 ? "+" : ""}${format.short(v)}`,
      },
    }),
    yAxis: {
      type: "category",
      data: sorted.map((item) => item.name),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: theme.text,
        fontSize: narrow ? 11 : 12,
        margin: narrow ? 8 : 14,
        fontFamily: theme.font,
        width: narrow ? 92 : 200,
        overflow: "truncate",
        formatter: (v: string) => (v === highlight ? `{hl|${v}}` : v),
        rich: { hl: { color: theme.bad, fontWeight: 700, fontSize: narrow ? 11 : 12, fontFamily: theme.font } },
      },
    },
    series: [
      {
        name: valueTitle,
        type: "bar",
        barWidth: 14,
        data: sorted.map((item) => {
          const up = item.value >= 0;
          const hl = item.name === highlight;
          const inside = hl && Math.abs(item.value) >= maxAbs * 0.5;
          return {
            value: item.value,
            itemStyle: {
              color: hl ? theme.bad : up ? theme.pos : theme.neg,
              borderRadius: up ? [0, radius, radius, 0] : [radius, 0, 0, radius],
            },
            label: {
              show: true,
              position: inside ? (up ? "insideRight" : "insideLeft") : up ? "right" : "left",
              distance: inside ? 8 : 6,
              formatter: `${item.value > 0 ? "+" : ""}${format.full(item.value)}`,
              color: inside ? "#ffffff" : hl ? theme.bad : theme.muted,
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

/** A ranked list of things as soft horizontal bars, the largest in the accent. */
function ranked(items: Item[], theme: ChartTheme, valueTitle: string, format: Format, narrow: boolean): Record<string, unknown> {
  // ECharts draws the first category at the bottom; a reader expects the
  // query's first row at the top.
  const ordered = [...items].reverse();
  const negative = items.every((item) => item.value <= 0);
  const extreme = items.reduce(
    (best, item) => (Math.abs(item.value) > Math.abs(best) ? item.value : best),
    0,
  );
  return {
    textStyle: { fontFamily: theme.font },
    animationDuration: 900,
    animationEasing: "cubicOut",
    grid: grid(6, narrow ? 48 : 64),
    tooltip: tooltip(theme, {
      trigger: "axis",
      axisPointer: { type: "shadow", shadowStyle: { color: rgba(theme.muted, 0.07) } },
      valueFormatter: (v: number) => format.full(v),
    }),
    xAxis: valueAxis(theme, format, { axisLabel: { show: false }, splitLine: { show: false } }),
    yAxis: {
      type: "category",
      data: ordered.map((item) => item.name),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: theme.text,
        fontSize: narrow ? 11 : 12,
        margin: narrow ? 8 : 14,
        fontFamily: theme.font,
        width: narrow ? 92 : 200,
        overflow: "truncate",
      },
    },
    series: [
      {
        name: valueTitle,
        type: "bar",
        barWidth: 14,
        data: ordered.map((item) => ({
          value: item.value,
          itemStyle: {
            color:
              item.value === extreme
                ? negative
                  ? theme.bad
                  : theme.accent
                : negative
                  ? theme.neg
                  : theme.pos,
            borderRadius: negative ? [6, 0, 0, 6] : [0, 6, 6, 0],
          },
        })),
        label: {
          show: true,
          position: negative ? "left" : "right",
          distance: 6,
          formatter: (p: { value: number }) => format.full(p.value),
          color: theme.muted,
          fontSize: 11.5,
          fontWeight: 500,
          fontFamily: theme.font,
        },
        animationDelay: (i: number) => i * 45,
      },
    ],
  };
}

function titleOf(spec: Record<string, unknown>): string | null {
  if (typeof spec.title === "string" && spec.title.length > 0) return spec.title;
  const nested = spec.title as { text?: unknown } | undefined;
  return nested && typeof nested.text === "string" ? nested.text : null;
}

/**
 * The figure for a spec, or null when the spec is outside the vocabulary.
 *
 * Pure: the same spec and theme always give the same option, which is what the
 * unit tests hold it to.
 */
export function buildChart(
  spec: Record<string, unknown>,
  theme: ChartTheme,
  context: { width?: number } = {},
): BuiltChart | null {
  const narrow = (context.width ?? 800) < 520;
  const mark = markOf(spec.mark);
  const encoding = (spec.encoding ?? {}) as Record<string, unknown>;
  const x = channel(encoding.x);
  const y = channel(encoding.y);
  const color = channel(encoding.color);
  const data = (spec.data ?? {}) as { values?: unknown };
  const rows = Array.isArray(data.values)
    ? data.values.filter((row): row is Row => !!row && typeof row === "object")
    : [];
  if (!mark || !["bar", "line", "point", "area"].includes(mark) || !x || !y || rows.length === 0) {
    return null;
  }

  const title = titleOf(spec) ?? `${y.title} by ${x.title.toLowerCase()}`;
  const format = formatFor(spec);
  const temporal = x.type === "temporal";

  // Categories along x, in a reader's order: time ascending, otherwise the
  // query's own order.
  let keys: string[] = [];
  let labels: string[] = [];
  if (temporal) {
    const unique = new Map<string, Date>();
    for (const row of rows) {
      const date = toDate(row[x.field]);
      if (date) unique.set(String(row[x.field]), date);
    }
    const sorted = [...unique.entries()].sort((a, b) => a[1].getTime() - b[1].getTime());
    const dates = sorted.map((entry) => entry[1]);
    const grain = grainOf(x, dates);
    const spansYears = new Set(dates.map((date) => date.getFullYear())).size > 1;
    keys = sorted.map((entry) => entry[0]);
    labels = dates.map((date) => formatDate(date, grain, spansYears));
  } else {
    const seen = new Set<string>();
    for (const row of rows) {
      const key = String(row[x.field] ?? "—");
      if (!seen.has(key)) {
        seen.add(key);
        keys.push(key);
      }
    }
    labels = keys.map((key) => {
      const asNumber = x.type === "quantitative" ? toNumber(key) : null;
      return asNumber === null ? key : fullNumber(asNumber);
    });
  }
  if (keys.length === 0) return null;

  const by = color ? color.title.toLowerCase() : null;
  const subtitle =
    temporal && labels.length > 1
      ? `${labels[0]} – ${labels[labels.length - 1]}${by ? ` · split by ${by}` : ""}`
      : by
        ? `Split by ${by}`
        : `${labels.length.toLocaleString()} ${labels.length === 1 ? "item" : "items"} · ${y.title.toLowerCase()}`;

  // One series per colour value, aligned to the categories.
  const seriesNames = color ? [...new Set(rows.map((row) => String(row[color.field] ?? "—")))] : [y.title];
  const valueAt = (seriesName: string, key: string): number | null => {
    const row = rows.find(
      (candidate) =>
        String(candidate[x.field] ?? "—") === key &&
        (!color || String(candidate[color.field] ?? "—") === seriesName),
    );
    return row ? toNumber(row[y.field]) : null;
  };
  const series = seriesNames.map((name) => ({ name, values: keys.map((key) => valueAt(name, key)) }));
  const palette = theme.categories;

  if (mark === "bar" && !color && !temporal && keys.length <= 24) {
    const items = keys.map((key, index) => ({
      name: labels[index] ?? key,
      value: series[0]?.values[index] ?? 0,
    }));
    const hasNeg = items.some((item) => item.value < 0);
    const hasPos = items.some((item) => item.value > 0);
    const option =
      hasNeg && hasPos
        ? diverging(items, theme, y.title, format, narrow)
        : ranked(items, theme, y.title, format, narrow);
    return { option, title, subtitle, height: Math.min(640, Math.max(170, items.length * 30 + 30)) };
  }

  const many = keys.length > 12;
  const base: Record<string, unknown> = {
    textStyle: { fontFamily: theme.font },
    animationDuration: 1000,
    animationEasing: "cubicOut",
    color: palette,
    grid: grid(color ? 40 : 14),
    tooltip: tooltip(theme, {
      trigger: mark === "point" ? "item" : "axis",
      valueFormatter: (v: number | null | undefined) =>
        v === null || v === undefined ? "—" : format.full(v),
    }),
    ...(color ? { legend: legend(theme) } : {}),
  };

  if (mark === "point") {
    return {
      title,
      subtitle,
      height: 300,
      option: {
        ...base,
        xAxis: categoryAxis(theme, labels, { boundaryGap: false }),
        yAxis: valueAxis(theme, format),
        series: series.map((entry, index) => ({
          name: entry.name,
          type: "scatter",
          symbolSize: 9,
          itemStyle: { color: color ? palette[index % palette.length] : theme.accent, opacity: 0.85 },
          data: entry.values,
        })),
      },
    };
  }

  if (mark === "bar") {
    const rotate = many && labels.some((label) => label.length > 8) ? 35 : 0;
    return {
      title,
      subtitle,
      height: color ? 320 : 290,
      option: {
        ...base,
        xAxis: categoryAxis(theme, labels, {
          axisLabel: { color: theme.muted, fontSize: 11, fontFamily: theme.font, hideOverlap: true, rotate },
        }),
        yAxis: valueAxis(theme, format),
        series: series.map((entry, index) => ({
          name: entry.name,
          type: "bar",
          barMaxWidth: color ? 18 : 30,
          itemStyle: {
            color: color ? palette[index % palette.length] : theme.accent,
            borderRadius: [6, 6, 0, 0],
          },
          ...(!color && !many
            ? {
                label: {
                  show: true,
                  position: "top",
                  formatter: (p: { value: number }) => format.short(p.value),
                  color: theme.muted,
                  fontSize: 11,
                  fontFamily: theme.font,
                },
              }
            : {}),
          data: entry.values,
          animationDelay: (i: number) => i * 40,
        })),
      },
    };
  }

  // line | area: a smooth line, with a soft area under a single series.
  const single = series.length === 1;
  return {
    title,
    subtitle,
    height: color ? 320 : 280,
    option: {
      ...base,
      xAxis: categoryAxis(theme, labels, {
        boundaryGap: false,
        axisLabel: {
          color: theme.muted,
          fontSize: 11,
          fontFamily: theme.font,
          hideOverlap: true,
          alignMinLabel: "left",
          alignMaxLabel: "right",
        },
      }),
      yAxis: valueAxis(theme, format),
      series: series.map((entry, index) => {
        const tone = single ? theme.accent : (palette[index % palette.length] ?? theme.accent);
        return {
          name: entry.name,
          type: "line",
          smooth: 0.35,
          symbol: "circle",
          symbolSize: 7,
          showSymbol: keys.length <= 12,
          lineStyle: { width: single ? 2.6 : 2, color: tone },
          itemStyle: { color: tone },
          ...(single || mark === "area" ? { areaStyle: { color: fade(tone, single ? 0.2 : 0.12) } } : {}),
          data: entry.values,
        };
      }),
    },
  };
}
