// The answer mini-markdown (architecture 09, "Text markup"): **bold**,
// <good> (green), <bad> (red) and <mark> (accent). This is a small
// tokenizer that builds React nodes, never HTML: anything that is not
// one of those four well-formed spans renders as literal text, so
// answer data cannot inject markup.
import { Fragment, type ReactNode } from "react";

const TOKEN =
  /(\*\*.+?\*\*|<good>.*?<\/good>|<bad>.*?<\/bad>|<mark>.*?<\/mark>)/gs;

const TONE_CLASS = {
  good: "font-semibold text-good-ink",
  bad: "font-semibold text-bad-ink",
  mark: "rounded bg-accent-soft px-0.5 font-semibold text-accent-ink",
} as const;

function renderInline(text: string): ReactNode[] {
  const parts = text
    .split(TOKEN)
    .filter((part) => part !== undefined && part !== "");
  return parts.map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length >= 5) {
      return <strong key={index}>{renderInline(part.slice(2, -2))}</strong>;
    }
    const tone = part.match(/^<(good|bad|mark)>(.*)<\/(good|bad|mark)>$/s);
    if (tone !== null && tone[1] === tone[3]) {
      return (
        <span key={index} className={TONE_CLASS[tone[1] as keyof typeof TONE_CLASS]}>
          {renderInline(tone[2])}
        </span>
      );
    }
    return <Fragment key={index}>{part}</Fragment>;
  });
}

export function Markup({ text }: { text: string }) {
  return <>{renderInline(text)}</>;
}
