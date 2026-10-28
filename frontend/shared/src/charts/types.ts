export interface ChartItem {
  name: string;
  value: number;
  label: string;
}

export interface ChartFormat {
  axis: (v: number) => string;
  tooltip?: (v: number) => string;
  // Exact per-point label by series data index. Used by answer charts
  // so duplicate values keep their own labels; kit demos omit it.
  tooltipByIndex?: (index: number) => string | undefined;
}

export interface Series {
  name: string;
  // Null plots as a gap: missing values stay missing, never invented zeros.
  values: (number | null)[];
}

/** Compact count axis, e.g. 1500 -> "1.5K". */
export function fmtNum(v: number): string {
  return new Intl.NumberFormat("en", { notation: "compact" }).format(v);
}
