import { ArrowDown } from "lucide-react";

export function ScrollToLatest({ onJump }: { onJump: () => void }) {
  return (
    <button
      type="button"
      onClick={onJump}
      className="absolute bottom-4 left-1/2 inline-flex -translate-x-1/2 cursor-pointer items-center gap-1.5 rounded-full border border-border bg-surface px-4 py-2 text-[13px] font-medium text-text-2 shadow-[0_6px_18px_rgba(var(--shadow-rgb),.12)] transition-[border-color,color] duration-200 hover:border-focus hover:text-text"
    >
      <ArrowDown size={15} aria-hidden="true" />
      Jump to latest
    </button>
  );
}
