import { useState } from "react";
import { Button } from "../components/Button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
} from "../components/Dialog";
import { Field } from "../components/Input";
import { Textarea } from "../components/Textarea";

// Suggest a change to a published entry (P12.2 shape). The suggestion goes
// to the learner; the displayed entry never rewrites itself.
export function SuggestChangeDialog({
  entryName,
  saving = false,
  serverError = null,
  onSave,
  onClose,
}: {
  entryName: string;
  saving?: boolean;
  serverError?: string | null;
  onSave: (text: string) => void;
  onClose: () => void;
}) {
  const [value, setValue] = useState("");
  const [blank, setBlank] = useState(false);
  const error = blank ? "Write your suggestion first." : serverError;
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent aria-label={`Suggest a change to ${entryName}`}>
        <DialogTitle>Suggest a change</DialogTitle>
        <DialogDescription>
          Your suggestion goes to the Learner, which checks it against the data. “{entryName}”
          stays as it is until then.
        </DialogDescription>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (value.trim() === "") {
              setBlank(true);
              return;
            }
            onSave(value.trim());
          }}
        >
          <Field label="Your suggestion" htmlFor="knowledge-suggest" error={error ?? undefined}>
            <Textarea
              id="knowledge-suggest"
              rows={4}
              value={value}
              placeholder="For example: lunch should start at 10:30 on weekends"
              onChange={(event) => {
                setValue(event.target.value);
                setBlank(false);
              }}
              aria-invalid={error ? true : undefined}
            />
          </Field>
          <DialogFooter>
            <Button variant="ghost" type="button" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={saving}>
              {saving ? "Sending…" : "Send suggestion"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
