import { useState } from "react";
import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
  Field,
  Textarea,
} from "@charie/shared";

// "What's wrong with it?" (P04.8). A note helps, but the box can stay
// empty: then only the flag goes to the learner's to-do list.
export function MarkWrongDialog({
  entryName,
  saving = false,
  serverError = null,
  onSave,
  onClose,
}: {
  entryName: string;
  saving?: boolean;
  serverError?: string | null;
  onSave: (note: string | null) => void;
  onClose: () => void;
}) {
  const [note, setNote] = useState("");
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent aria-label={`Mark ${entryName} as wrong`}>
        <DialogTitle>What&apos;s wrong with it?</DialogTitle>
        <DialogDescription>
          The Learner looks at it again in the next learning run. A note helps, but you can leave
          it empty.
        </DialogDescription>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            onSave(note.trim() === "" ? null : note.trim());
          }}
        >
          <Field
            label="What is wrong?"
            htmlFor="knowledge-wrong-note"
            error={serverError ?? undefined}
          >
            <Textarea
              id="knowledge-wrong-note"
              rows={4}
              value={note}
              placeholder="For example: lunch ends at 2:30 pm, not 3 pm."
              onChange={(event) => setNote(event.target.value)}
              aria-invalid={serverError ? true : undefined}
            />
          </Field>
          <DialogFooter>
            <Button variant="ghost" type="button" onClick={onClose}>
              Cancel
            </Button>
            <Button variant="danger" type="submit" disabled={saving}>
              {saving ? "Marking…" : "Mark as wrong"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
