// Plain-text rendering of a saved answer for Copy (P03.8). Only readable
// content crosses over: follow-up chips are UI buttons, so the follow_ups
// block is omitted, and control labels (Copy, expand, download) never
// enter the text because it is built from block data, not the DOM.
import type {
  Answer,
  AnswerBlock,
  Cell,
  ChartBlock,
  KpiItem,
  MethodBlock,
  TableBlock,
  TreeBlock,
} from "../api/chat-types";
import type { TreeNode } from "../charts/tree";

function cellText(cell: Cell): string {
  if (cell === null || cell === undefined) return "";
  if (typeof cell === "number") return String(cell);
  if (typeof cell === "object") return cell.f;
  return cell;
}

function chartText(block: ChartBlock): string {
  const lines = [block.title];
  if (block.subtitle !== undefined && block.subtitle !== "") lines.push(block.subtitle);
  const columns = block.data.columns.join(" | ");
  const rows = block.data.rows.map((row) => row.map(cellText).join(" | "));
  return [...lines, columns, ...rows].join("\n");
}

function tableText(block: TableBlock): string {
  const header = block.columns.map((column) => column.label).join(" | ");
  const rows = block.rows.map((row) =>
    block.columns.map((column) => cellText(row[column.key])).join(" | "),
  );
  return [block.title, header, ...rows].join("\n");
}

function treeLines(nodes: TreeNode[]): string[] {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const children = new Map<string | null, TreeNode[]>();
  for (const node of nodes) {
    const siblings = children.get(node.parent) ?? [];
    siblings.push(node);
    children.set(node.parent, siblings);
  }
  const lines: string[] = [];
  const seen = new Set<string>();
  function walk(id: string, depth: number): void {
    if (seen.has(id)) return;
    seen.add(id);
    const node = byId.get(id);
    if (node === undefined) return;
    lines.push(`${"  ".repeat(depth)}- ${node.label}${node.value ? ` (${node.value})` : ""}`);
    for (const child of children.get(id) ?? []) walk(child.id, depth + 1);
  }
  for (const root of children.get(null) ?? []) walk(root.id, 0);
  // Orphans (missing parents, dup-id loops already visited) still print.
  for (const node of nodes) {
    if (!seen.has(node.id)) walk(node.id, 0);
  }
  return lines;
}

function treeText(block: TreeBlock): string {
  return [block.title, ...treeLines(block.nodes)].join("\n");
}

function kpiText(item: KpiItem): string {
  let line = `${item.label}: ${item.value}`;
  if (item.change !== undefined && item.change !== "") {
    line += ` (${item.change}${item.compare ? ` vs ${item.compare}` : ""})`;
  } else if (item.compare !== undefined && item.compare !== "") {
    line += ` (vs ${item.compare})`;
  }
  return line;
}

function methodText(block: MethodBlock): string {
  const lines = ["How I worked this out"];
  if (block.definitions.length > 0) lines.push("What this means", ...block.definitions);
  if (block.steps.length > 0) lines.push("Steps", ...block.steps);
  for (const query of block.queries) {
    lines.push(`Data used: ${query.purpose}`, query.sql);
  }
  for (const source of block.sources) {
    lines.push(
      `Source: ${source.document}, ${source.location}`,
      `"${source.quote}"`,
    );
  }
  return lines.join("\n");
}

export function blockText(block: AnswerBlock): string {
  switch (block.type) {
    case "reading":
      return block.text;
    case "text":
      return block.paragraphs
        .map((paragraph) => paragraph.sentences.map((sentence) => sentence.text).join(" "))
        .join("\n\n");
    case "kpis":
      return block.items.map(kpiText).join("\n");
    case "chart":
      return chartText(block);
    case "table":
      return tableText(block);
    case "tree":
      return treeText(block);
    case "callout":
      return block.text;
    case "suggestions":
      return [
        ...(block.title !== undefined && block.title !== "" ? [block.title] : []),
        ...block.items.map((item) => `${item.text} (${item.confidence})`),
      ].join("\n");
    case "method":
      return methodText(block);
    case "follow_ups":
      // UI buttons, not copyable prose.
      return "";
    default:
      return "";
  }
}

/** The whole answer as readable prose, blocks separated by blank lines. */
export function answerText(answer: Answer): string {
  return answer.blocks
    .map(blockText)
    .filter((text) => text !== "")
    .join("\n\n");
}
