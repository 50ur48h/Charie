"use client";

/** The composer (design: `.composer`): a soft rounded box that grows with the question. */

import { ArrowUp, Brain, Paperclip } from "lucide-react";
import { useEffect, useId, useImperativeHandle, useRef, type Ref } from "react";

import { Hint } from "@/components/ui/tooltip";
import { modelName, type ModelChoice } from "@/lib/models";
import { cn } from "@/lib/utils";

export function Composer({
  label,
  value,
  onChange,
  onSend,
  disabled = false,
  sending = false,
  placeholder = "Ask Charie anything about your business…",
  onAttach,
  inputRef,
  footnote = true,
  className,
  minRows = 1,
  model,
}: {
  /** The field's accessible name, e.g. "Ask a question". */
  label: string;
  value: string;
  onChange: (next: string) => void;
  onSend: () => void;
  disabled?: boolean;
  sending?: boolean;
  placeholder?: string;
  /** What the paperclip does. */
  onAttach?: (() => void) | undefined;
  inputRef?: Ref<HTMLTextAreaElement> | undefined;
  footnote?: boolean;
  className?: string | undefined;
  minRows?: number;
  /** The Meta model picker; absent shows the plain "Thinking" pill. */
  model?: ModelChoice | undefined;
}) {
  const id = useId();
  const box = useRef<HTMLTextAreaElement | null>(null);
  // The parent focuses the field (a follow-up chip fills it, say).
  useImperativeHandle(inputRef, () => box.current as HTMLTextAreaElement, []);

  // Grow with the question, up to a point, then scroll.
  useEffect(() => {
    const area = box.current;
    if (!area) return;
    area.style.height = "auto";
    area.style.height = `${Math.min(area.scrollHeight, 220)}px`;
  }, [value]);

  const canSend = !disabled && !sending && value.trim().length > 0;

  return (
    <div className={cn("w-full font-sans", className)}>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (canSend) onSend();
        }}
        className={cn(
          "rounded-[24px] border border-border bg-surface pt-3.5 pr-3 pb-2.5 pl-[18px] shadow-[0_6px_24px_rgba(var(--shadow-rgb),.07)] transition-[box-shadow,border-color] focus-within:border-focus focus-within:shadow-[0_10px_32px_rgba(var(--shadow-rgb),.1)]",
          disabled && "opacity-80",
        )}
      >
        <label htmlFor={id} className="sr-only">
          {label}
        </label>
        <textarea
          id={id}
          ref={box}
          rows={minRows}
          maxLength={4000}
          value={value}
          disabled={disabled || sending}
          placeholder={placeholder}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              if (canSend) onSend();
            }
          }}
          className="block max-h-[220px] min-h-[26px] w-full resize-none border-0 bg-transparent text-[15.5px] leading-normal text-text outline-none placeholder:text-placeholder disabled:cursor-not-allowed"
        />
        <div className="mt-1.5 flex items-center gap-1.5">
          {onAttach && (
            <Hint label="Add documents">
              <button
                type="button"
                aria-label="Add documents"
                onClick={onAttach}
                className="grid size-8 place-items-center rounded-sm text-muted-foreground transition-colors hover:bg-surface-2 hover:text-text"
              >
                <Paperclip aria-hidden="true" className="size-[17px]" />
              </button>
            </Hint>
          )}
          {model?.choices && model.model ? (
            <Hint label="The Meta model that answers this question">
              <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-full border border-border px-2.5 py-[5px] text-[12.5px] text-text-2 focus-within:border-focus">
                <Brain aria-hidden="true" className="size-3.5 text-brand" />
                <span className="sr-only">Meta model</span>
                <select
                  value={model.model}
                  onChange={(event) => model.setModel(event.target.value)}
                  disabled={sending}
                  className="cursor-pointer bg-transparent text-text-2 outline-none"
                >
                  {model.choices.models.map((option) => (
                    <option key={option.id} value={option.id}>
                      {option.name}
                    </option>
                  ))}
                </select>
              </label>
            </Hint>
          ) : (
            <Hint label="Charie plans, queries and checks its work before it answers">
              <span className="inline-flex cursor-default items-center gap-1.5 rounded-full border border-border px-2.5 py-[5px] text-[12.5px] text-text-2">
                <Brain aria-hidden="true" className="size-3.5 text-brand" />
                Thinking
              </span>
            </Hint>
          )}
          <button
            type="submit"
            aria-label="Send"
            disabled={!canSend}
            className="ml-auto grid size-[34px] place-items-center rounded-full bg-brand text-on-brand transition-[transform,background-color,opacity] hover:scale-105 hover:bg-brand-hover disabled:pointer-events-none disabled:opacity-40"
          >
            {sending ? (
              <span
                aria-hidden="true"
                className="size-4 animate-spin rounded-full border-2 border-on-brand/40 border-t-on-brand"
              />
            ) : (
              <ArrowUp aria-hidden="true" className="size-[18px] stroke-[2.2]" />
            )}
          </button>
        </div>
      </form>
      {footnote && (
        <p className="mt-2 text-center text-[12px] text-muted-foreground">
          {model?.model
            ? `Answered by Meta ${modelName(model.model)} (${model.model}) through the Meta Model API. `
            : ""}
          Charie shows the query behind every number.
        </p>
      )}
    </div>
  );
}
