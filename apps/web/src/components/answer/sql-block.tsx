"use client";

/** A SQL statement, verbatim, with its keywords and strings tinted. */

import { useEffect, useId, useRef } from "react";

import { cn } from "@/lib/utils";

const KEYWORDS =
  /\b(SELECT|DISTINCT|FROM|WHERE|AND|OR|NOT|IN|IS|NULL|AS|ON|JOIN|LEFT|RIGHT|INNER|OUTER|FULL|CROSS|GROUP|BY|ORDER|HAVING|LIMIT|OFFSET|UNION|ALL|WITH|CASE|WHEN|THEN|ELSE|END|ASC|DESC|BETWEEN|LIKE|ILIKE|OVER|PARTITION|COUNT|SUM|AVG|MIN|MAX|COALESCE|CAST|DATE_TRUNC|EXTRACT|ROUND|TOP|TRUE|FALSE)\b/gi;
const STRINGS = /'(?:[^']|'')*'/g;

interface HighlightLike {
  add(range: Range): void;
  delete(range: Range): boolean;
}
interface HighlightRegistry {
  get(name: string): HighlightLike | undefined;
  set(name: string, value: HighlightLike): void;
}

function registry(): { highlights: HighlightRegistry; make: () => HighlightLike } | null {
  if (typeof window === "undefined") return null;
  const css = (window as unknown as { CSS?: { highlights?: HighlightRegistry } }).CSS;
  const Ctor = (window as unknown as { Highlight?: new () => HighlightLike }).Highlight;
  if (!css?.highlights || !Ctor) return null;
  ensureHighlightStyles();
  return { highlights: css.highlights, make: () => new Ctor() };
}

/** The two `::highlight()` rules, added at run time. */
function ensureHighlightStyles(): void {
  if (document.getElementById("sql-highlight-styles")) return;
  const style = document.createElement("style");
  style.id = "sql-highlight-styles";
  style.textContent =
    "::highlight(sql-kw){color:var(--code-kw)}::highlight(sql-str){color:var(--code-str)}";
  document.head.appendChild(style);
}

function ranges(node: Text, pattern: RegExp): Range[] {
  const found: Range[] = [];
  const text = node.data;
  pattern.lastIndex = 0;
  for (let match = pattern.exec(text); match; match = pattern.exec(text)) {
    const range = document.createRange();
    range.setStart(node, match.index);
    range.setEnd(node, match.index + match[0].length);
    found.push(range);
  }
  return found;
}

export function SqlBlock({ sql, className }: { sql: string; className?: string | undefined }) {
  const code = useRef<HTMLElement | null>(null);
  const id = useId();

  useEffect(() => {
    const api = registry();
    const text = code.current?.firstChild;
    if (!api || !text || text.nodeType !== Node.TEXT_NODE) return;
    const added: [string, Range][] = [];
    for (const [name, pattern] of [
      ["sql-kw", KEYWORDS],
      ["sql-str", STRINGS],
    ] as const) {
      let highlight = api.highlights.get(name);
      if (!highlight) {
        highlight = api.make();
        api.highlights.set(name, highlight);
      }
      for (const range of ranges(text as Text, pattern)) {
        highlight.add(range);
        added.push([name, range]);
      }
    }
    return () => {
      for (const [name, range] of added) api.highlights.get(name)?.delete(range);
    };
  }, [sql, id]);

  return (
    <pre
      className={cn(
        "m-0 overflow-x-auto rounded-md bg-code px-3.5 py-3 font-mono text-[12.5px] leading-[1.65] whitespace-pre-wrap text-code-ink [word-break:break-word]",
        className,
      )}
    >
      <code ref={code}>{sql}</code>
    </pre>
  );
}
