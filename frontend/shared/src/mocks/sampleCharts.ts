import type { ChartFormat, ChartItem, Series } from "../charts/types";
import type { TreeNode } from "../charts/tree";

/** Axis "+10%", tooltip "+14.8%", with a real minus sign. */
export const percentFormat: ChartFormat = {
  axis: (v) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(Math.round(v))}%`,
  tooltip: (v) =>
    `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(1)}%`,
};

const thousands = (v: number): string => {
  const abs = Math.abs(v);
  const trim = (n: number): string => n.toFixed(1).replace(/\.0$/, "");
  if (abs >= 1e6) return `$${trim(v / 1e6)}M`;
  if (abs >= 1e3) return `$${trim(v / 1e3)}K`;
  return `$${v}`;
};

/** Compact thousands, e.g. "$96.2K". */
export const thousandsFormat: ChartFormat = { axis: thousands, tooltip: thousands };

/** Whole dollars on the axis ("$2"), cents in the tooltip ("$1.22"). */
export const dollarFormat: ChartFormat = {
  axis: (v) => `$${v}`,
  tooltip: (v) => `$${v.toFixed(2)}`,
};

export const SALES_CHANGE: { items: ChartItem[]; highlight: string[] } = {
  items: [
    { name: "Dallas Uptown", value: 14.8, label: "+14.8%" },
    { name: "Houston Heights", value: 12.1, label: "+12.1%" },
    { name: "Domain Northside", value: 10.6, label: "+10.6%" },
    { name: "San Antonio Pearl", value: 9.4, label: "+9.4%" },
    { name: "Deep Ellum", value: 8.7, label: "+8.7%" },
    { name: "Montrose", value: 7.9, label: "+7.9%" },
    { name: "South Congress", value: 6.3, label: "+6.3%" },
    { name: "Plano Legacy", value: 5.1, label: "+5.1%" },
    { name: "Katy Grand", value: -1.2, label: "−1.2%" },
    { name: "Galleria", value: -2.4, label: "−2.4%" },
    { name: "Downtown Austin", value: -18.2, label: "−18.2%" },
  ],
  highlight: ["Downtown Austin"],
};

export const DELIVERY_PER_DAY: {
  labels: string[];
  series: Series[];
  band: { from: string; to: string; label: string };
} = {
  labels: Array.from({ length: 26 }, (_, i) => `${i + 1} Oct`),
  series: [
    {
      name: "Delivery orders",
      values: [
        224, 259, 287, 246, 211, 196, 214, 226, 271, 276, 255, 202, 207, 121,
        38, 92, 262, 244, 199, 203, 208, 217, 268, 283, 247, 209,
      ],
    },
    {
      name: "Normal day",
      values: [
        220, 265, 280, 250, 205, 200, 210, 220, 265, 280, 250, 205, 200, 210,
        220, 265, 280, 250, 205, 200, 210, 220, 265, 280, 250, 205,
      ],
    },
  ],
  band: { from: "14 Oct", to: "16 Oct", label: "Delivery app outage" },
};

export const TOP_RESTAURANTS: { items: ChartItem[]; highlight: string[] } = {
  items: [
    { name: "Downtown Austin", value: 96200, label: "$96.2K" },
    { name: "Dallas Uptown", value: 88400, label: "$88.4K" },
    { name: "Houston Heights", value: 81900, label: "$81.9K" },
    { name: "Domain Northside", value: 76300, label: "$76.3K" },
    { name: "Galleria", value: 61200, label: "$61.2K" },
  ],
  highlight: ["Downtown Austin"],
};

export const NET_SALES_SPARK = [302, 310, 305, 318, 322, 330, 327, 341];

const QUESTIONS_PER_DAY = [
  0.84, 1.22, 0.65, 0.31, 1.48, 1.62, 1.35, 1.1, 1.71, 0.52, 0.28, 1.56,
  1.83, 1.44, 1.29, 2.1, 0.66, 0.37, 1.52, 1.95, 1.38, 1.27, 1.66, 0.72,
  0.41, 1.19, 0.97,
];

export const COST_PER_DAY: {
  labels: string[];
  series: Series[];
  labelEvery: number;
} = {
  labels: QUESTIONS_PER_DAY.map((_, i) => `${i + 1} Oct`),
  series: [
    {
      name: "Learning",
      values: QUESTIONS_PER_DAY.map((_, i) => (i === 2 ? 7.2 : i === 19 ? 2.6 : 0)),
    },
    { name: "Questions", values: QUESTIONS_PER_DAY },
  ],
  labelEvery: 4,
};

export const DROP_TREE: TreeNode[] = [
  { id: "downtown", parent: null, label: "Downtown Austin", value: "−$21.4K", tone: "bad" },
  { id: "delivery", parent: "downtown", label: "Delivery", value: "−$18.9K", tone: "bad" },
  {
    id: "outage",
    parent: "delivery",
    label: "Outage (14–16 Oct)",
    value: "−$17.2K",
    tone: "bad",
    highlight: true,
  },
  { id: "other-days", parent: "delivery", label: "Other days", value: "−$1.7K", tone: "bad" },
  { id: "dine-in", parent: "downtown", label: "Dine-in", value: "−$3.1K", tone: "bad" },
  { id: "lunch", parent: "dine-in", label: "Lunch", value: "−$2.4K", tone: "bad" },
  { id: "dinner", parent: "dine-in", label: "Dinner", value: "−$0.7K", tone: "bad" },
  { id: "pickup", parent: "downtown", label: "Pickup", value: "+$0.6K", tone: "good" },
];
