// The answer mini-markdown (architecture 09, "Text markup"): **bold**,
// <good> (green), <bad> (red) and <mark> (accent). This is a small
// single-pass scanner that builds React nodes, never HTML: anything that
// is not one of those four well-formed spans renders as literal text, so
// answer data cannot inject markup. There are no backtracking patterns:
// each character is visited once per nesting level, so long runs of
// unclosed tags stay linear instead of hanging the UI thread.
import { Fragment, type ReactNode } from "react";

type ToneName = "good" | "bad" | "mark";

const TONE_CLASS = {
  good: "font-semibold text-good-ink",
  bad: "font-semibold text-bad-ink",
  mark: "rounded bg-accent-soft px-0.5 font-semibold text-accent-ink",
} as const;

const TONE_CLOSE: Record<ToneName, string> = {
  good: "</good>",
  bad: "</bad>",
  mark: "</mark>",
};

const TAGS = ["<good>", "<bad>", "<mark>", "</good>", "</bad>", "</mark>"];

interface Span {
  start: number;
  end: number;
  name: ToneName | "bold";
  innerStart: number;
  innerEnd: number;
}

// One linear pass collecting every candidate: overlapping ** runs and
// <good>/<bad>/<mark> open and close tags. Only fixed strings are
// compared, so the scan is O(n).
function collect(text: string): {
  stars: number[];
  opens: { name: ToneName; pos: number; end: number }[];
  closes: { name: ToneName; pos: number }[];
} {
  const stars: number[] = [];
  const opens: { name: ToneName; pos: number; end: number }[] = [];
  const closes: { name: ToneName; pos: number }[] = [];
  let i = 0;
  while (i < text.length) {
    const char = text[i];
    if (char === "*" && text[i + 1] === "*") {
      stars.push(i);
      i += 1;
    } else if (char === "<") {
      const tag = TAGS.find((candidate) => text.startsWith(candidate, i));
      if (tag === undefined) {
        i += 1;
      } else if (tag.startsWith("</")) {
        closes.push({ name: tag.slice(2, -1) as ToneName, pos: i });
        i += tag.length;
      } else {
        opens.push({ name: tag.slice(1, -1) as ToneName, pos: i, end: i + tag.length });
        i += tag.length;
      }
    } else {
      i += 1;
    }
  }
  return { stars, opens, closes };
}

// Pair greedily in document order, matching the old format exactly: a **
// run pairs with the first later run at least 3 chars on (one char of
// content, so **** stays literal); a tone opener pairs with the next
// closer of the same name. Unpaired candidates stay literal text.
function pairSpans(
  text: string,
  collected: ReturnType<typeof collect>,
): Span[] {
  const spans: Span[] = [];
  const stars = collected.stars;
  let s = 0;
  while (s < stars.length) {
    const open = stars[s];
    let c = s + 1;
    while (c < stars.length && stars[c] - open < 3) c += 1;
    if (c < stars.length) {
      spans.push({
        start: open,
        end: stars[c] + 2,
        name: "bold",
        innerStart: open + 2,
        innerEnd: stars[c],
      });
      s = c + 1;
    } else {
      s += 1;
    }
  }
  for (const name of ["good", "bad", "mark"] as const) {
    const closerPos = collected.closes
      .filter((close) => close.name === name)
      .map((close) => close.pos);
    let c = 0;
    for (const open of collected.opens) {
      if (open.name !== name) continue;
      while (c < closerPos.length && closerPos[c] < open.end) c += 1;
      if (c < closerPos.length) {
        const closeEnd = closerPos[c] + TONE_CLOSE[name].length;
        spans.push({
          start: open.pos,
          end: closeEnd,
          name,
          innerStart: open.end,
          innerEnd: closerPos[c],
        });
        c += 1;
      }
    }
  }
  spans.sort((a, b) => a.start - b.start);
  return spans;
}

function renderInline(text: string): ReactNode[] {
  const spans = pairSpans(text, collect(text));
  const nodes: ReactNode[] = [];
  let cursor = 0;
  let key = 0;
  for (const span of spans) {
    // A span that starts inside an already-emitted span is content, not a
    // new construct: skip it and let the outer span's recursion own it.
    if (span.start < cursor) continue;
    if (span.start > cursor) {
      nodes.push(<Fragment key={key++}>{text.slice(cursor, span.start)}</Fragment>);
    }
    const inner = renderInline(text.slice(span.innerStart, span.innerEnd));
    if (span.name === "bold") {
      nodes.push(<strong key={key++}>{inner}</strong>);
    } else {
      nodes.push(
        <span key={key++} className={TONE_CLASS[span.name]}>
          {inner}
        </span>,
      );
    }
    cursor = span.end;
  }
  if (cursor < text.length) {
    nodes.push(<Fragment key={key++}>{text.slice(cursor)}</Fragment>);
  }
  return nodes;
}

export function Markup({ text }: { text: string }) {
  return <>{renderInline(text)}</>;
}
