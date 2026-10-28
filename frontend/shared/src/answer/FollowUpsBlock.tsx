import { ArrowRight } from "lucide-react";
import type { FollowUpsBlock as FollowUpsBlockType } from "../api/chat-types";

export function FollowUpsBlock({
  block,
  onFollowUp,
}: {
  block: FollowUpsBlockType;
  onFollowUp: (text: string) => void;
}) {
  return (
    <div className="follow-ups mb-4 flex flex-wrap gap-2 print:hidden">
      {block.items.map((item) => (
        <button
          key={item}
          type="button"
          onClick={() => onFollowUp(item)}
          className="inline-flex cursor-pointer items-center gap-1.5 rounded-full border border-border bg-surface px-4 py-2 text-[13.5px] font-medium text-text-2 transition-[border-color,color] duration-200 hover:border-focus hover:text-text"
        >
          {item}
          <ArrowRight size={14} aria-hidden="true" className="text-muted" />
        </button>
      ))}
    </div>
  );
}
