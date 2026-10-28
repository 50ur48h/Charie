// "This is wrong" dialog (P03.8): sends the correction to the learner
// to-do list through POST /api/messages/{id}/wrong. The answer itself
// never changes here. A failed send keeps the dialog open with the text
// preserved; only a success clears and closes it.
import { useRef, useState } from "react";
import { ApiError } from "../api/client";
import { toast } from "../components/Toast";
import { Button } from "../components/Button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
} from "../components/Dialog";
import { useWrongMessage } from "../api/chats";

export function WrongAnswerDialog({
  messageId,
  open,
  onOpenChange,
}: {
  messageId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [correction, setCorrection] = useState("");
  const [sending, setSending] = useState(false);
  const inflight = useRef(false);
  const wrongMessage = useWrongMessage();
  const blank = correction.trim() === "";

  async function send(): Promise<void> {
    if (blank || inflight.current) return;
    inflight.current = true;
    setSending(true);
    try {
      await wrongMessage.mutateAsync({ messageId, correction: correction.trim() });
      setCorrection("");
      onOpenChange(false);
      toast("Sent to the Learner to check.");
    } catch (error) {
      toast(
        error instanceof ApiError
          ? error.message
          : "Couldn't send the correction. Try again.",
      );
    } finally {
      inflight.current = false;
      setSending(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>Tell Charie what&apos;s wrong</DialogTitle>
        <DialogDescription>What&apos;s wrong? Charie&apos;s learner will look into it.</DialogDescription>
        <label className="mt-4 block">
          <span className="sr-only">What is wrong?</span>
          <textarea
            value={correction}
            onChange={(event) => setCorrection(event.target.value)}
            placeholder="For example: sales should not include delivery fees"
            rows={4}
            className="mt-1 block w-full resize-y rounded-card border border-border bg-bg px-4 py-3 text-[14.5px] leading-relaxed text-text placeholder:text-muted focus:border-focus focus:outline-none"
          />
        </label>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="primary" disabled={blank || sending} onClick={() => void send()}>
            {sending ? "Sending…" : "Send correction"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
