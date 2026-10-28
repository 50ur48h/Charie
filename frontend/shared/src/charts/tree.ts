import type { EChartsCoreOption } from "echarts/core";
import type { ChartTheme } from "../theme/chartTheme";
import { escHtml, mix, solid, tooltipStyle } from "./helpers";

export interface TreeNode {
  id: string;
  parent: string | null;
  label: string;
  value?: string;
  tone?: "good" | "bad" | "neutral";
  highlight?: boolean;
}

export interface BuiltTreeNode {
  label: string;
  value?: string;
  tone?: "good" | "bad" | "neutral";
  highlight?: boolean;
  children: BuiltTreeNode[];
}

/**
 * Turn the flat answer-format list into the nested shape ECharts needs.
 * Children keep the list's order. A node whose parent doesn't exist is left
 * out. Without exactly one top node there is no tree, so this returns null.
 */
export function buildTree(nodes: TreeNode[]): BuiltTreeNode | null {
  const roots = nodes.filter((node) => node.parent === null);
  if (roots.length !== 1) return null;
  const convert = (node: TreeNode): BuiltTreeNode => ({
    label: node.label,
    ...(node.value === undefined ? {} : { value: node.value }),
    ...(node.tone === undefined ? {} : { tone: node.tone }),
    ...(node.highlight === undefined ? {} : { highlight: node.highlight }),
    children: nodes.filter((child) => child.parent === node.id).map(convert),
  });
  return convert(roots[0]);
}

function boxWidth(label: string, value: string | undefined): number {
  const longest = Math.max(label.length, value?.length ?? 0);
  return Math.max(116, Math.round(longest * 7.4 + 34));
}

function widestBox(node: BuiltTreeNode): number {
  return Math.max(
    boxWidth(node.label, node.value),
    ...node.children.map(widestBox),
  );
}

interface EChartTreeNode {
  name: string;
  labelText: string;
  valueText?: string;
  symbol: "roundRect";
  symbolSize: [number, number];
  itemStyle: {
    color: string;
    borderColor: string;
    borderWidth: number;
    shadowColor: string;
    shadowBlur: number;
    shadowOffsetY: number;
  };
  label: {
    position: "inside";
    formatter: string;
    rich: Record<string, unknown>;
  };
  children: EChartTreeNode[];
}

export function treeOption(nodes: TreeNode[], theme: ChartTheme): EChartsCoreOption {
  const root = buildTree(nodes);
  if (!root) {
    return {
      textStyle: { fontFamily: theme.font },
      series: [{ type: "tree", data: [] }],
    };
  }
  const side = widestBox(root) / 2 + 8;
  const colorOf = (node: BuiltTreeNode): string =>
    node.highlight
      ? solid(theme.bad)
      : node.tone === "bad"
        ? solid(theme.negStrong)
        : node.tone === "good"
          ? solid(theme.posStrong)
          : theme.muted;
  const inkOf = (node: BuiltTreeNode): string =>
    node.highlight || node.tone === "bad"
      ? solid(theme.badInk)
      : node.tone === "good"
        ? solid(theme.goodInk)
        : theme.muted;
  const convert = (node: BuiltTreeNode): EChartTreeNode => {
    const c = colorOf(node);
    return {
      name: node.label,
      labelText: node.label,
      ...(node.value === undefined ? {} : { valueText: node.value }),
      symbol: "roundRect",
      symbolSize: [boxWidth(node.label, node.value), 42],
      itemStyle: {
        color: node.highlight ? mix(theme.nodeBg, c, 0.1) : theme.nodeBg,
        borderColor: node.highlight ? c : theme.nodeBorder || theme.grid,
        borderWidth: node.highlight ? 1.5 : 1,
        shadowColor: "rgba(15,20,30,0.07)",
        shadowBlur: 12,
        shadowOffsetY: 3,
      },
      label: {
        position: "inside",
        formatter:
          node.value === undefined
            ? `{n|${node.label}}`
            : `{n|${node.label}}\n{v|${node.value}}`,
        rich: {
          n: {
            color: theme.text,
            fontSize: 12,
            fontWeight: 600,
            lineHeight: 17,
            fontFamily: theme.font,
            align: "center",
          },
          v: {
            color: inkOf(node),
            fontSize: 12.5,
            fontWeight: 700,
            lineHeight: 17,
            fontFamily: theme.font,
            align: "center",
          },
        },
      },
      children: node.children.map(convert),
    };
  };
  return {
    textStyle: { fontFamily: theme.font },
    animationDuration: 800,
    animationDurationUpdate: 600,
    tooltip: {
      ...tooltipStyle(theme),
      trigger: "item",
      formatter: (p: unknown) => {
        const data = (p as { data?: { labelText?: string; valueText?: string } }).data;
        if (!data) return "";
        return data.valueText === undefined
          ? escHtml(data.labelText ?? "")
          : `${escHtml(data.labelText ?? "")}: <b>${escHtml(data.valueText)}</b>`;
      },
    },
    series: [
      {
        type: "tree",
        data: [convert(root)],
        orient: "LR",
        top: 24,
        bottom: 24,
        left: side,
        right: side,
        edgeShape: "curve",
        initialTreeDepth: -1,
        expandAndCollapse: false,
        roam: false,
        lineStyle: { color: theme.edge || theme.grid, width: 1.6, curveness: 0.5 },
        label: { position: "inside" },
        leaves: { label: { position: "inside" } },
        emphasis: { focus: "descendant" },
      },
    ],
  };
}
