// The row under a saved answer (P03.8, approved Calm player design):
// Copy, Good answer / Not helpful votes, "This is wrong" and the
// "All numbers checked" badge. Votes post optimistically and restore the
// prior vote when the request fails.
import { useRef, useState } from "react";
import { Copy, Flag, ShieldCheck, ThumbsDown, ThumbsUp } from "lucide-react";
import { ApiError } from "../api/client";
import { toast } from "../components/Toast";
import { useFeedback, type FeedbackVote } from "../api/chats";
import { answerText } from "./answerText";
import type { Answer } from "./types";
import { WrongAnswerDialog } from "./WrongAnswerDialog";

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

const actionClass =
  "inline-flex cursor-pointer items-center gap-1.5 rounded-full px-3 py-[7px] text-[13px] font-medium text-text-2 transition-[background-color,color] duration-200 not-disabled:hover:bg-surface-2 not-disabled:hover:text-text disabled:cursor-not-allowed disabled:opacity-50";

const votedClass = "bg-accent-soft text-accent-ink";

export function AnswerActions({
  messageId,
  answer,
  initialVote,
}: {
  messageId: number;
  answer: Answer;
  initialVote: FeedbackVote;
}) {
  // The saved vote from the last load; voting updates it optimistically.
  const [vote, setVote] = useState<FeedbackVote>(initialVote);
  const [wrongOpen, setWrongOpen] = useState(false);
  const inflight = useRef(false);
  const feedback = useFeedback();

  async function choose(next: Exclude<FeedbackVote, null>): Promise<void> {
    if (inflight.current) return;
    const previous = vote;
    const cleared = previous === next ? null : next;
    inflight.current = true;
    setVote(cleared);
    try {
      await feedback.mutateAsync({ messageId, vote: cleared });
      if (cleared !== null) toast("Thanks for the feedback.");
    } catch (error) {
      setVote(previous);
      toast(
        error instanceof ApiError ? error.message : "Couldn't save the vote. Try again.",
      );
    } finally {
      inflight.current = false;
    }
  }

  async function copy(): Promise<void> {
    const ok = await copyText(answerText(answer));
    toast(ok ? "Answer copied." : "Couldn't copy the answer.");
  }

  return (
    <>
      <div className="answer-actions mb-4 flex flex-wrap items-center gap-1 print:hidden">
        <button type="button" title="Copy the answer" onClick={() => void copy()} className={actionClass}>
          <Copy size={15} aria-hidden="true" className="text-muted" />
          <span>Copy</span>
        </button>
        <button
          type="button"
          title="Good answer"
          aria-label="Good answer"
          aria-pressed={vote === "up"}
          onClick={() => void choose("up")}
          className={`${actionClass} ${vote === "up" ? votedClass : ""}`}
        >
          <ThumbsUp size={15} aria-hidden="true" className="text-muted" />
        </button>
        <button
          type="button"
          title="Not helpful"
          aria-label="Not helpful"
          aria-pressed={vote === "down"}
          onClick={() => void choose("down")}
          className={`${actionClass} ${vote === "down" ? votedClass : ""}`}
        >
          <ThumbsDown size={15} aria-hidden="true" className="text-muted" />
        </button>
        <button
          type="button"
          title="Tell Charie what's wrong"
          onClick={() => setWrongOpen(true)}
          className={actionClass}
        >
          <Flag size={15} aria-hidden="true" className="text-muted" />
          <span>This is wrong</span>
        </button>
        <span className="ml-1 inline-flex items-center gap-1.5 text-[12.5px] text-muted">
          <ShieldCheck size={15} aria-hidden="true" />
          All numbers checked
        </span>
      </div>
      <WrongAnswerDialog messageId={messageId} open={wrongOpen} onOpenChange={setWrongOpen} />
    </>
  );
}
