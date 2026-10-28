export interface ChartItem {
  name: string;
  value: number;
  label: string;
}

export interface ChartFormat {
  axis: (v: number) => string;
  tooltip?: (v: number) => string;
}

export interface Series {
  name: string;
  values: number[];
}

/** Compact count axis, e.g. 1500 -> "1.5K". */
export function fmtNum(v: number): string {
  return new Intl.NumberFormat("en", { notation: "compact" }).format(v);
}
