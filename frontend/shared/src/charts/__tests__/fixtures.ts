import type { ChartTheme } from "../../theme/chartTheme";

const base: ChartTheme = {
  font: "Inter",
  gridType: "dashed",
  barRadius: 6,
  barWidth: 14,
  text: "#1F2937",
  muted: "#7A8477",
  grid: "#E2E7DD",
  accent: "#5B8C5A",
  pos: "#B5CDB9",
  neg: "#EBC2BB",
  bad: "#C0392B",
  posStrong: "#2E7D32",
  negStrong: "#C0392B",
  nodeBg: "#FFFFFF",
  nodeBorder: "#E2E7DD",
  edge: "#CBD5C7",
  tooltipBg: "#FFFFFF",
  tooltipBorder: "#E2E7DD",
};

export const light: ChartTheme = base;

export const dark: ChartTheme = {
  ...base,
  text: "#EDEAE2",
  muted: "#8E8A9E",
  grid: "#2E2B3A",
  tooltipBg: "#1E1C28",
  tooltipBorder: "#3A3650",
  nodeBg: "#1E1C28",
  nodeBorder: "#3A3650",
  edge: "#3A3650",
};
