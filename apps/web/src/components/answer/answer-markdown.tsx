"use client";

/** The answer's words, with their structure shown rather than flattened. */

import { ChartColumn, Download, FileSpreadsheet, Table2 } from "lucide-react";
import { isValidElement, memo, useCallback, useMemo, useState, type ReactNode } from "react";
import Markdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { toast } from "sonner";

import { cn } from "@/lib/utils";

import { looksNumeric, markTone } from "./cells";
import { buildChart, readChartTheme } from "./chart-option";
import { DataTable, downloadCsv } from "./data-table";
import { EChart, exportPng } from "./echart";
import { Figure, FigureAction } from "./figure";
import { KpiGrid, type Kpi } from "./kpi";
import { deriveChart } from "./table-chart";

interface HastNode {
  type: string;
  tagName?: string;
  value?: string;
  children?: HastNode[];
}

interface MdastNode {
  type: string;
  value?: string;
  children?: MdastNode[];
  data?: Record<string, unknown>;
}

function textOfNode(node: HastNode | undefined): string {
  if (!node) return "";
  if (node.type === "text") return node.value ?? "";
  return (node.children ?? []).map(textOfNode).join("");
}

/** The plain text of rendered children, for deciding how a phrase reads. */
export function flatten(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(flatten).join("");
  if (isValidElement(node)) {
    return flatten((node.props as { children?: ReactNode }).children);
  }
  return "";
}

const DIRECTION =
  "(?:up|down|rose|risen|fell|fallen|grew|grown|dropped|increased|decreased|gained|lost|declined|jumped|climbed|slipped|dipped|surged|plunged)";
const AMOUNT =
  "(?:by\\s+)?(?:[+\\-−]\\s?)?(?:RM|MYR|USD|\\$|€|£)?\\s?\\d[\\d,]*(?:\\.\\d+)?(?:\\s?(?:%|percent|pts?|[KMB]\\b))?";

/** Where a phrase should be highlighted: `==explicit==`, or a change with a direction. */
const HIGHLIGHT = new RegExp(
  `==([^=\\n]+?)==|\\b${DIRECTION}\\s+${AMOUNT}|(?<![\\w.])[+−]\\d+(?:\\.\\d+)?%`,
  "gi",
);

/** Nodes whose text is not prose to highlight: a bold phrase decides for itself. */
const SKIP = new Set(["strong", "emphasis", "link", "heading", "inlineCode", "code", "highlight"]);
const DIRECTION_END = new RegExp(`\\b${DIRECTION}(?:\\s+by)?\\s*$`, "i");
const ONLY_AMOUNT = new RegExp(`^${AMOUNT}$`, "i");

function plainOf(node: MdastNode): string {
  return node.value ?? (node.children ?? []).map(plainOf).join("");
}

function highlighted(value: string): MdastNode {
  const tone = markTone(value);
  return {
    type: "highlight",
    data: { hName: "mark", hProperties: tone ? { className: [tone] } : {} },
    children: [{ type: "text", value }],
  };
}

function remarkHighlight() {
  const split = (value: string): MdastNode[] => {
    const parts: MdastNode[] = [];
    let last = 0;
    HIGHLIGHT.lastIndex = 0;
    for (let match = HIGHLIGHT.exec(value); match; match = HIGHLIGHT.exec(value)) {
      const explicit = match[1];
      const inner = explicit ?? match[0];
      const tone = markTone(inner);
      // An implicit highlight needs a direction; an explicit one does not.
      if (explicit === undefined && !tone) continue;
      if (match.index > last) parts.push({ type: "text", value: value.slice(last, match.index) });
      parts.push(highlighted(inner));
      last = match.index + match[0].length;
    }
    if (parts.length === 0) return [{ type: "text", value }];
    if (last < value.length) parts.push({ type: "text", value: value.slice(last) });
    return parts;
  };
  const walk = (node: MdastNode) => {
    if (!node.children || SKIP.has(node.type)) return;
    const next: MdastNode[] = [];
    for (let index = 0; index < node.children.length; index++) {
      const child = node.children[index]!;
      const following = node.children[index + 1];
      // Markdown often separates the direction from its bold number.
      const direction = child.type === "text" ? DIRECTION_END.exec(child.value ?? "") : null;
      if (direction && following?.type === "strong" && ONLY_AMOUNT.test(plainOf(following))) {
        const prefix = child.value!.slice(0, direction.index);
        let phrase = direction[0] + plainOf(following);
        const previous = next[next.length - 1];
        if (prefix.trim() === "," && previous?.type === "strong" && !looksNumeric(plainOf(previous))) {
          next.pop();
          phrase = plainOf(previous) + prefix + phrase;
        } else if (prefix) next.push(...split(prefix));
        next.push(highlighted(phrase));
        index++;
        continue;
      }
      if (child.type === "text" && child.value) next.push(...split(child.value));
      else {
        walk(child);
        next.push(child);
      }
    }
    node.children = next;
  };
  return (tree: MdastNode) => walk(tree);
}

function rowsOf(table: HastNode): { columns: string[]; rows: string[][] } {
  let columns: string[] = [];
  const rows: string[][] = [];
  const visit = (node: HastNode, inHead: boolean) => {
    if (node.type !== "element") return;
    if (node.tagName === "tr") {
      const cells = (node.children ?? [])
        .filter((cell) => cell.type === "element" && (cell.tagName === "th" || cell.tagName === "td"))
        .map((cell) => textOfNode(cell).trim());
      if (inHead || (columns.length === 0 && rows.length === 0 && node.children?.some((cell) => cell.tagName === "th"))) {
        columns = cells;
      } else {
        rows.push(cells);
      }
      return;
    }
    for (const child of node.children ?? []) visit(child, inHead || node.tagName === "thead");
  };
  visit(table, false);
  const width = Math.max(columns.length, ...rows.map((row) => row.length));
  while (columns.length < width) columns.push("");
  return { columns, rows: rows.map((row) => Array.from({ length: width }, (_, index) => row[index] ?? "")) };
}

const METRIC_HEADER = /^(metrics?|measures?|kpis?|indicators?|key figures?|figures?|stats?|statistics?)$/i;
const VALUE_HEADER = /^(values?|amounts?|totals?|results?)$/i;
const CHANGE_HEADER = /(change|vs\.?|delta|growth|difference|trend)/i;
const COMPARISON_HEADER = /^(comparison|baseline|period|note)$/i;

/** "$1.42M (+6.2%)" → the value and its change. */
function splitDelta(label: string, value: string): Kpi {
  const match = /^(.*?)\s*\(\s*([+\-−]\s?[^)]*)\)\s*$/.exec(value);
  return match ? { label, value: match[1] ?? value, delta: match[2] } : { label, value };
}

/** Number cards, when a table is really a short list of figures. */
export function kpisFrom(columns: string[], rows: string[][]): Kpi[] | null {
  // One row of nothing but figures: the headers are the labels.
  if (
    rows.length === 1 &&
    columns.length >= 2 &&
    columns.length <= 4 &&
    columns.every((column) => column.trim().length > 0) &&
    rows[0]!.every((cell) => looksNumeric(cell))
  ) {
    return columns.map((label, index) => splitDelta(label, rows[0]![index] ?? ""));
  }
  if (rows.length === 0 || rows.length > 6) return null;
  const metricTable = METRIC_HEADER.test((columns[0] ?? "").trim()) || VALUE_HEADER.test((columns[1] ?? "").trim());
  if (!metricTable) return null;
  if (rows.some((row) => !(row[0] ?? "").trim() || !(row[1] ?? "").trim())) return null;
  if (columns.length === 2) return rows.map(([label = "", value = ""]) => splitDelta(label, value));
  if (
    (columns.length === 3 ||
      (columns.length === 4 && COMPARISON_HEADER.test((columns[3] ?? "").trim()))) &&
    CHANGE_HEADER.test(columns[2] ?? "")
  ) {
    return rows.map(([label = "", value = "", delta = "", note = ""]) => ({
      label,
      value,
      ...(delta.trim() ? { delta: delta.trim() } : {}),
      ...(note.trim() ? { note: note.trim() } : {}),
    }));
  }
  return null;
}

function ViewSwitch({ view, onChange }: { view: "chart" | "table"; onChange: (next: "chart" | "table") => void }) {
  const option = (value: "chart" | "table", label: string, icon: ReactNode) => (
    <button
      type="button"
      aria-pressed={view === value}
      onClick={() => onChange(value)}
      className={cn(
        "inline-flex h-7 items-center gap-1.5 rounded-[8px] px-2.5 text-[12.5px] font-medium transition-colors [&_svg]:size-3.5",
        view === value ? "bg-surface text-text shadow-[0_1px_2px_rgba(var(--shadow-rgb),.08)]" : "text-muted-foreground hover:text-text",
      )}
    >
      {icon}
      {label}
    </button>
  );
  return (
    <div className="inline-flex rounded-[10px] bg-surface-2 p-0.5" role="group" aria-label="Show as">
      {option("chart", "Chart", <ChartColumn aria-hidden="true" />)}
      {option("table", "Table", <Table2 aria-hidden="true" />)}
    </div>
  );
}

function TableBlock({ node }: { node: HastNode | undefined }) {
  const { columns, rows } = useMemo(() => (node ? rowsOf(node) : { columns: [], rows: [] }), [node]);
  const kpis = useMemo(() => kpisFrom(columns, rows), [columns, rows]);
  const derived = useMemo(() => (kpis ? null : deriveChart(columns, rows)), [kpis, columns, rows]);
  const built = useMemo(() => (derived ? buildChart(derived.spec, readChartTheme()) : null), [derived]);
  const [view, setView] = useState<"chart" | "table">("chart");
  const makeOption = useCallback(
    (width: number) => (derived ? (buildChart(derived.spec, readChartTheme(), { width })?.option ?? null) : null),
    [derived],
  );

  if (!node || columns.length === 0) return null;
  if (kpis) return <KpiGrid items={kpis} />;

  const csv = () => downloadCsv(built?.title ?? "answer-table", columns, rows);
  const png = async () => {
    if (!derived || !built) return;
    const theme = readChartTheme();
    const option = buildChart(derived.spec, theme)?.option;
    const url = option ? await exportPng(option, 760, built.height, theme.surface) : null;
    if (!url) return toast("The image could not be made in this browser.");
    const link = document.createElement("a");
    link.href = url;
    link.download = `${built.title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "chart"}.png`;
    link.click();
  };

  if (!derived || !built) {
    return (
      <Figure className="px-3 pt-2 pb-2 sm:px-4">
        <DataTable columns={columns.map((label) => ({ label }))} rows={rows} />
        <div className="mt-1 flex items-center justify-between border-t border-border-soft pt-2 text-[12px] text-muted-foreground">
          <span>
            {rows.length.toLocaleString()} {rows.length === 1 ? "row" : "rows"}
          </span>
          <button
            type="button"
            aria-label="Download as CSV"
            onClick={csv}
            className="inline-flex items-center gap-1.5 rounded-sm px-2 py-1 transition-colors hover:bg-surface-2 hover:text-text"
          >
            <FileSpreadsheet aria-hidden="true" className="size-3.5" />
            CSV
          </button>
        </div>
      </Figure>
    );
  }

  return (
    <Figure
      title={built.title}
      subtitle={`${rows.length.toLocaleString()} ${rows.length === 1 ? "row" : "rows"} · from the table in this answer`}
      controls={<ViewSwitch view={view} onChange={setView} />}
      actions={
        view === "chart" ? (
          <FigureAction label="Download as image" onClick={() => void png()}>
            <Download />
          </FigureAction>
        ) : (
          <FigureAction label="Download as CSV" onClick={csv}>
            <FileSpreadsheet />
          </FigureAction>
        )
      }
    >
      {view === "chart" ? (
        <EChart testId="table-chart" makeOption={makeOption} height={built.height} />
      ) : (
        <DataTable columns={columns.map((label) => ({ label }))} rows={rows} />
      )}
    </Figure>
  );
}

const components: Components = {
  strong: ({ children }) => {
    const tone = markTone(flatten(children));
    return tone ? <mark className={tone}>{children}</mark> : <strong>{children}</strong>;
  },
  table: ({ node }) => <TableBlock node={node as unknown as HastNode | undefined} />,
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noreferrer noopener">
      {children}
    </a>
  ),
};

const remarkPlugins = [remarkGfm, remarkHighlight];

/** Memoised on the words, so a poll elsewhere on the page never redraws a chart. */
export const AnswerMarkdown = memo(function AnswerMarkdown({
  words,
  className,
}: {
  words: string;
  className?: string | undefined;
}) {
  return (
    <div className={className ? `prose-answer ${className}` : "prose-answer"} data-testid="answer-text">
      <Markdown remarkPlugins={remarkPlugins} components={components}>
        {words}
      </Markdown>
    </div>
  );
});
