export interface ChartTheme {
  font: string;
  gridType: string;
  barRadius: number;
  barWidth: number;
  text: string;
  muted: string;
  grid: string;
  accent: string;
  pos: string;
  neg: string;
  bad: string;
  badInk: string;
  goodInk: string;
  accentInk: string;
  posStrong: string;
  negStrong: string;
  nodeBg: string;
  nodeBorder: string;
  edge: string;
  tooltipBg: string;
  tooltipBorder: string;
}

export function chartTheme(): ChartTheme {
  const vars = getComputedStyle(document.documentElement);
  const v = (name: string): string => vars.getPropertyValue(name).trim();
  return {
    font: "Inter",
    gridType: "dashed",
    barRadius: 6,
    barWidth: 14,
    text: v("--text"),
    muted: v("--chart-muted"),
    grid: v("--chart-grid"),
    accent: v("--accent"),
    pos: v("--chart-pos"),
    neg: v("--chart-neg"),
    bad: v("--bad"),
    badInk: v("--bad-ink"),
    goodInk: v("--good-ink"),
    accentInk: v("--accent-ink"),
    posStrong: v("--good"),
    negStrong: v("--bad"),
    nodeBg: v("--surface"),
    nodeBorder: v("--border"),
    edge: v("--chart-edge"),
    tooltipBg: v("--surface"),
    tooltipBorder: v("--border"),
  };
}
