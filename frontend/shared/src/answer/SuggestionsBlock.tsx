import type { SuggestionsBlock as SuggestionsBlockType } from "../api/chat-types";
import { Markup } from "./markup";

// Suggested next actions. The confidence label is the model's own word,
// shown verbatim: Charie never reinterprets it (architecture 05).
export function SuggestionsBlock({ block }: { block: SuggestionsBlockType }) {
  return (
    <div className="mb-4">
      {block.title !== undefined && block.title !== "" && (
        <h3 className="m-0 mb-2 text-[14px] font-semibold text-text">{block.title}</h3>
      )}
      <ul className="m-0 list-disc space-y-1.5 pl-5 text-[14.5px] leading-relaxed text-text-2">
        {block.items.map((item) => (
          <li key={item.text}>
            <Markup text={item.text} />{" "}
            <span className="text-[12.5px] text-muted">· {item.confidence}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
