import { describe, expect, it } from "vitest";
import { buildTree, treeOption } from "../tree";
import { DROP_TREE } from "../../mocks";
import { light } from "./fixtures";

describe("buildTree", () => {
  it("nests the flat list", () => {
    expect(buildTree(DROP_TREE)).toEqual({
      label: "Downtown Austin",
      value: "−$21.4K",
      tone: "bad",
      children: [
        {
          label: "Delivery",
          value: "−$18.9K",
          tone: "bad",
          children: [
            {
              label: "Outage (14–16 Oct)",
              value: "−$17.2K",
              tone: "bad",
              highlight: true,
              children: [],
            },
            { label: "Other days", value: "−$1.7K", tone: "bad", children: [] },
          ],
        },
        {
          label: "Dine-in",
          value: "−$3.1K",
          tone: "bad",
          children: [
            { label: "Lunch", value: "−$2.4K", tone: "bad", children: [] },
            { label: "Dinner", value: "−$0.7K", tone: "bad", children: [] },
          ],
        },
        { label: "Pickup", value: "+$0.6K", tone: "good", children: [] },
      ],
    });
  });

  it("returns null without exactly one top node", () => {
    expect(buildTree([])).toBeNull();
    expect(
      buildTree([
        { id: "a", parent: null, label: "A" },
        { id: "b", parent: null, label: "B" },
      ]),
    ).toBeNull();
  });

  it("leaves out nodes whose parent is missing", () => {
    const tree = buildTree([
      { id: "a", parent: null, label: "A" },
      { id: "orphan", parent: "ghost", label: "Orphan" },
    ]);
    expect(tree).toEqual({ label: "A", children: [] });
  });
});

interface TestNode {
  symbolSize: [number, number];
  itemStyle: { borderColor: string; borderWidth: number };
  label: { rich: { v: { color: string } } };
  children: TestNode[];
}

function rootNode(): TestNode {
  const option = treeOption(DROP_TREE, light) as {
    series: [{ data: [TestNode]; left: number; right: number }];
  };
  return option.series[0].data[0];
}

describe("treeOption", () => {
  it("colors bad nodes with the theme's bad color", () => {
    const root = rootNode();
    expect(root.label.rich.v.color).toBe(light.negStrong);
    const pickup = root.children[2];
    expect(pickup.label.rich.v.color).toBe(light.posStrong);
  });

  it("makes boxes wide enough for the longest text", () => {
    const option = treeOption(DROP_TREE, light) as {
      series: [{ data: [TestNode]; left: number; right: number }];
    };
    const [series] = option.series;
    expect(series.data[0].symbolSize).toEqual([145, 42]);
    expect(series.left).toBe(167 / 2 + 8);
    expect(series.right).toBe(167 / 2 + 8);
  });

  it("escapes markup in tooltip labels and values", () => {
    const nodes = [
      {
        id: "evil",
        parent: null,
        label: '<script>alert("x")</script>',
        value: "<b>bad</b>",
        tone: "bad" as const,
      },
    ];
    const option = treeOption(nodes, light) as {
      tooltip: { formatter: (p: { data: { labelText: string; valueText: string } }) => string };
    };
    const html = option.tooltip.formatter({
      data: { labelText: '<script>alert("x")</script>', valueText: "<b>bad</b>" },
    });
    expect(html).not.toContain("<script");
    expect(html).not.toContain("<b>bad");
    expect(html).toContain("&lt;script&gt;");
    expect(html).toContain("&lt;b&gt;bad&lt;/b&gt;");
  });

  it("highlights the highlighted node", () => {
    const root = rootNode();
    const outage = root.children[0].children[0];
    const other = root.children[0].children[1];
    expect(outage.itemStyle.borderWidth).toBe(1.5);
    expect(outage.itemStyle.borderColor).toBe(light.bad);
    expect(other.itemStyle.borderWidth).toBe(1);
    expect(other.itemStyle.borderColor).toBe(light.nodeBorder);
  });
});
