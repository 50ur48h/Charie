"use client";

/**
 * Under the answer (design: `.a-actions`, `.a-follow`): copy, a quick reaction,
 * a way to say it is wrong, how the run ended — and a few next questions.
 *
 * **The ending is a word, and the true word** (B-133, D-044). A refusal and a
 * partial answer are correct outcomes rather than errors, so they are muted
 * rather than red, and a partial answer names its missing half. Only a run the
 * platform could not complete is red.
 */

import {
  CircleAlert,
  CircleSlash,
  CircleX,
  Copy,
  CornerDownRight,
  Flag,
  ShieldCheck,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Hint } from "@/components/ui/tooltip";
import type { Run } from "@/lib/api-client";
import { cn } from "@/lib/utils";

/** Plain words for a status, because colour never carries meaning alone. */
export const STATUS_WORDS: Record<string, string> = {
  queued: "queued",
  running: "working",
  validating: "checking",
  completed: "answered",
  interrupted: "interrupted",
  failed: "failed",
  budget_exhausted: "stopped at its budget",
};

/** How the run ended, or null when it has not said (runs before revision 0029). */
export function outcome(run: Run): string | null {
  return run.status === "completed" && run.state ? run.state : null;
}

/** The word for an ending — never "answered" on a refusal (B-133). */
export function endingWord(run: Run): string {
  const state = outcome(run);
  if (state === "refused") return "could not answer";
  if (state === "partly") {
    // A missing half that only says "answered…" names nothing; say "partly".
    const missing = run.unanswered?.trim() ?? "";
    return missing && !/^answered\b/i.test(missing) ? `could not answer ${missing}` : "partly answered";
  }
  return STATUS_WORDS[run.status] ?? run.status;
}

function Outcome({ run }: { run: Run }) {
  const failed = run.status === "failed";
  const state = outcome(run);
  const word = endingWord(run);
  const queries = run.findings.reduce((total, finding) => total + finding.support.length, 0);
  const unsupported = run.findings.length === 0 && !failed;

  const tone = failed
    ? "text-bad"
    : state === "refused"
      ? "text-muted-foreground"
      : state === "partly" || word !== "answered"
        ? "text-warn"
        : "text-good";
  const Icon = failed ? CircleX : state === "refused" ? CircleSlash : tone === "text-good" ? ShieldCheck : CircleAlert;

  return (
    <span className={cn("ml-auto inline-flex flex-wrap items-center gap-x-1.5 text-[12.5px] font-semibold", tone)}>
      <Icon aria-hidden="true" className="size-[15px]" />
      <span className="inline-block first-letter:uppercase">{word}</span>
      {unsupported ? (
        <>
          <span aria-hidden="true" className="font-normal text-muted-foreground">·</span>
          <span className="font-normal text-muted-foreground">no supporting query</span>
        </>
      ) : !failed && queries > 0 ? (
        <span className="font-normal text-muted-foreground">
          · backed by {queries} quer{queries === 1 ? "y" : "ies"}
        </span>
      ) : null}
    </span>
  );
}

function Act({
  label,
  onClick,
  pressed,
  children,
  iconOnly = false,
}: {
  label: string;
  onClick: () => void;
  pressed?: boolean | undefined;
  children: ReactNode;
  iconOnly?: boolean;
}) {
  return (
    <Hint label={label}>
      <button
        type="button"
        onClick={onClick}
        aria-pressed={pressed}
        aria-label={iconOnly ? label : undefined}
        className={cn(
          "inline-flex h-8 items-center gap-1.5 rounded-sm px-2.5 text-[13px] text-muted-foreground transition-colors hover:bg-surface-2 hover:text-text [&_svg]:size-4",
          pressed && "bg-brand-soft text-brand-ink hover:bg-brand-soft hover:text-brand-ink",
        )}
      >
        {children}
      </button>
    </Hint>
  );
}

async function copyText(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const area = document.createElement("textarea");
    area.value = text;
    area.style.cssText = "position:fixed;opacity:0";
    document.body.appendChild(area);
    area.select();
    document.execCommand("copy");
    area.remove();
  }
}

export function AnswerActions({
  run,
  words,
  onCorrect,
}: {
  run: Run;
  words: string | null;
  /** Sends a correction as the next message, so Charie takes another look. */
  onCorrect?: ((note: string) => void) | undefined;
}) {
  const [vote, setVote] = useState<"up" | "down" | null>(null);
  const [wrong, setWrong] = useState(false);
  const [note, setNote] = useState("");

  const react = (next: "up" | "down") => {
    const turningOn = vote !== next;
    setVote(turningOn ? next : null);
    if (turningOn) toast("Thanks for the feedback.");
  };

  return (
    <div className="mt-3.5 font-sans">
      <div className="flex flex-wrap items-center gap-0.5">
        {words && (
          <Act label="Copy the answer" onClick={() => void copyText(words).then(() => toast("Answer copied."))}>
            <Copy aria-hidden="true" />
            <span>Copy</span>
          </Act>
        )}
        <Act label="Good answer" iconOnly pressed={vote === "up"} onClick={() => react("up")}>
          <ThumbsUp aria-hidden="true" />
        </Act>
        <Act label="Not helpful" iconOnly pressed={vote === "down"} onClick={() => react("down")}>
          <ThumbsDown aria-hidden="true" />
        </Act>
        {onCorrect && (
          <Act label="Tell Charie what's wrong" pressed={wrong} onClick={() => setWrong((open) => !open)}>
            <Flag aria-hidden="true" />
            <span>This is wrong</span>
          </Act>
        )}
        <Outcome run={run} />
      </div>
      {onCorrect && (
        <div
          className={cn(
            "grid transition-[grid-template-rows] duration-400 ease-[cubic-bezier(.2,.8,.2,1)]",
            wrong ? "grid-rows-[1fr]" : "grid-rows-[0fr]",
          )}
        >
          <div className={cn("min-h-0 overflow-hidden", !wrong && "invisible")}>
            <form
              className="mt-2.5 grid gap-2.5 rounded-lg border border-border bg-surface p-3.5"
              onSubmit={(event) => {
                event.preventDefault();
                const text = note.trim();
                if (!text) return;
                onCorrect(text);
                setNote("");
                setWrong(false);
              }}
            >
              <label htmlFor={`wrong-${run.id}`} className="text-[13.5px] font-semibold">
                What’s wrong? Charie will take another look with your correction.
              </label>
              <textarea
                id={`wrong-${run.id}`}
                value={note}
                onChange={(event) => setNote(event.target.value)}
                rows={2}
                placeholder="For example: sales should not include delivery fees"
                className="min-h-16 w-full resize-y rounded-md border border-border bg-background px-3 py-2.5 text-[14px] outline-none focus:border-brand focus:ring-[3px] focus:ring-brand-soft"
              />
              <div className="flex justify-end gap-2">
                <Button variant="ghost" size="sm" onClick={() => setWrong(false)}>
                  Cancel
                </Button>
                <Button variant="primary" size="sm" type="submit" disabled={note.trim().length === 0}>
                  Send correction
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export function FollowUps({
  suggestions,
  onPick,
}: {
  suggestions: string[];
  onPick: (question: string) => void;
}) {
  if (suggestions.length === 0) return null;
  return (
    <div className="mt-4 animate-fade-up font-sans">
      <p className="mb-2 text-[12px] font-semibold text-muted-foreground">You might also ask</p>
      <div className="flex flex-wrap gap-2">
        {suggestions.map((question) => (
          <button
            key={question}
            type="button"
            onClick={() => onPick(question)}
            className="inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-2 text-left text-[13.5px] transition-[border-color,transform,color] hover:-translate-y-px hover:border-brand hover:text-brand-ink"
          >
            <CornerDownRight aria-hidden="true" className="size-[15px] text-muted-foreground" />
            <span>{question}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
