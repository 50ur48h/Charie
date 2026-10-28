import { useMemo, useRef } from "react";
import { Download } from "lucide-react";
import { Button } from "../components/Button";
import { Chart, type ChartHandle } from "../charts/Chart";
import { treeOption, type TreeNode } from "../charts/tree";
import type { ChartTheme } from "../theme/chartTheme";
import type { TreeBlock as TreeBlockType } from "../api/chat-types";

// A cycle reachable from the root would recurse forever inside the kit's
// builder, so the block validates first: exactly one root and no cycle
// reachable from it. Anything else gets a clear unavailable state instead
// of a hung page. Nodes the root cannot reach (missing parents) are left
// out, exactly like the kit does.
function reachableTree(nodes: TreeNode[]): boolean {
  const roots = nodes.filter((node) => node.parent === null);
  if (roots.length !== 1) return false;
  const children = new Map<string, TreeNode[]>();
  for (const node of nodes) {
    if (node.parent === null) continue;
    const list = children.get(node.parent) ?? [];
    list.push(node);
    children.set(node.parent, list);
  }
  // Depth-first walk of the reachable graph: meeting a node already on
  // the current path means a cycle. Diamonds (shared children) pass
  // through fine because nodes leave the path when fully explored.
  const onPath = new Set<string>();
  const visit = (id: string): boolean => {
    if (onPath.has(id)) return false;
    onPath.add(id);
    for (const child of children.get(id) ?? []) {
      if (!visit(child.id)) return false;
    }
    onPath.delete(id);
    return true;
  };
  return visit(roots[0].id);
}

export function TreeBlock({ block }: { block: TreeBlockType }) {
  const chartRef = useRef<ChartHandle>(null);
  const valid = useMemo(() => reachableTree(block.nodes), [block]);
  if (!valid) {
    return <p className="mb-4 text-[14px] text-muted">Tree unavailable.</p>;
  }
  return (
    <div className="mb-4 min-w-0 rounded-card border border-border bg-surface px-[18px] pb-3 pt-4 shadow-card">
      <div className="mb-2 font-serif text-[17px]">{block.title}</div>
      <div
        className="overflow-x-auto"
        role="region"
        aria-label={block.title}
        tabIndex={0}
      >
        <div className="min-w-[640px]">
          <Chart
            ref={chartRef}
            label={block.title}
            height={380}
            build={(theme: ChartTheme) => treeOption(block.nodes, theme)}
          />
        </div>
      </div>
      <div className="mt-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() => chartRef.current?.downloadPng(block.title)}
          aria-label={`Download as image: ${block.title}`}
        >
          <Download aria-hidden="true" />
          Download as image
        </Button>
      </div>
    </div>
  );
}
