import type { ReadingBlock as ReadingBlockType } from "../api/chat-types";
import { Markup } from "./markup";

// show_reading (settings key, architecture 05) controls only visibility:
// false hides the line, everything else in the answer still renders. The
// settings page (P03.13) will wire the real value; until then it defaults
// to true, matching the architecture default.
export function ReadingBlock({
  block,
  showReading = true,
}: {
  block: ReadingBlockType;
  showReading?: boolean;
}) {
  if (!showReading) return null;
  return (
    <p className="m-0 mb-4 text-[15.5px] leading-relaxed">
      <Markup text={block.text} />
    </p>
  );
}
