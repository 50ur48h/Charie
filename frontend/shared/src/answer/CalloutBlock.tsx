import type { CalloutBlock as CalloutBlockType } from "../api/chat-types";
import { Markup } from "./markup";

// Callout tones from the answer contract (P10.10: note or warn). An
// unknown tone falls back to the note look rather than crashing.
const TONE_CLASS = {
  note: "bg-accent-soft text-accent-ink",
  warn: "bg-warn-soft text-warn-ink",
} as const;

export function CalloutBlock({ block }: { block: CalloutBlockType }) {
  const toneClass =
    block.tone === "warn" ? TONE_CLASS.warn : TONE_CLASS.note;
  return (
    <div className={`callout-block mb-4 rounded-xl px-4 py-3 text-[14px] leading-relaxed ${toneClass}`}>
      <Markup text={block.text} />
    </div>
  );
}
