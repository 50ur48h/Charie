// The question box, shared by the new-chat page (P03.1) and the chat frame
// (P03.2). Thinking is the only mode: Quick stays visible but disabled until
// Phase 16, and there is no file attachment button.
import { useCallback, type KeyboardEvent, type Ref } from "react";
import { ArrowUp, Brain, Zap } from "lucide-react";
import { Textarea } from "../components/Textarea";
import { cn } from "../components/cn";

const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

export function formatDataThrough(isoDate: string): string {
  const [year, month, day] = isoDate.slice(0, 10).split("-").map(Number);
  if (!year || !month || !day) return isoDate;
  return `${day} ${MONTHS[month - 1] ?? month}`;
}

export interface QuestionComposerProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  sending?: boolean;
  dataThrough?: string | null;
  textareaRef?: Ref<HTMLTextAreaElement>;
  large?: boolean;
  disabled?: boolean;
  disabledPlaceholder?: string;
}

export function QuestionComposer({
  value,
  onChange,
  onSubmit,
  sending = false,
  dataThrough,
  textareaRef,
  large = false,
  disabled = false,
  disabledPlaceholder,
}: QuestionComposerProps) {
  const blank = value.trim() === "";

  const onKeyDown = useCallback(
    (event: KeyboardEvent<HTMLTextAreaElement>) => {
      // IME composition (e.g. CJK input) must not send mid-character.
      if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
        event.preventDefault();
        if (!blank && !sending && !disabled) onSubmit();
      }
    },
    [blank, onSubmit, sending, disabled],
  );

  return (
    <form
      className={cn(
        "rounded-[26px] border border-border bg-surface p-[18px_14px_12px_22px] shadow-[0_10px_30px_rgba(var(--shadow-rgb),.06)]",
      )}
      onSubmit={(event) => {
        event.preventDefault();
        if (!blank && !sending && !disabled) onSubmit();
      }}
    >
      <Textarea
        ref={textareaRef}
        aria-label="Ask a question"
        placeholder={disabled && disabledPlaceholder ? disabledPlaceholder : "For example: which restaurants grew the most this month, and why?"}
        rows={large ? 2 : 2}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={onKeyDown}
        disabled={disabled}
        className="border-0 bg-transparent p-0 text-[16.5px] shadow-none focus:shadow-none"
      />
      <div className="mt-2 flex flex-wrap items-center gap-x-1.5 gap-y-2 sm:gap-x-2">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-accent-soft px-3 py-1 text-[12.5px] font-medium text-accent-ink">
          <Brain size={14} aria-hidden="true" />
          Thinking
        </span>
        <span
          className="inline-flex cursor-not-allowed items-center gap-1.5 rounded-full bg-surface-2 px-3 py-1 text-[12.5px] font-medium text-muted opacity-70"
          title="Quick answers come later."
          aria-disabled="true"
        >
          <Zap size={14} aria-hidden="true" />
          Quick
        </span>
        {dataThrough == null ? null : (
          <span className="ml-1 inline-flex items-center gap-2 text-[12.5px] whitespace-nowrap text-muted sm:ml-2">
            <span aria-hidden="true" className="inline-block size-2 rounded-full bg-good" />
            {`Data up to ${formatDataThrough(dataThrough)}`}
          </span>
        )}
        <button
          type="submit"
          aria-label="Ask"
          title="Ask"
          disabled={blank || sending || disabled}
          className="ml-auto grid size-10 flex-none cursor-pointer place-items-center rounded-full bg-accent text-white shadow-button transition-transform duration-200 not-disabled:hover:-translate-y-px not-disabled:hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
        >
          <ArrowUp size={18} aria-hidden="true" />
        </button>
      </div>
    </form>
  );
}
