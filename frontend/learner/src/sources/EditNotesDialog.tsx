import { useEffect, useRef, useState } from "react";
import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
  Textarea,
  toast,
  useOwnerNotes,
  useSaveOwnerNotes,
} from "@charie/shared";

// The notes editor (setup step 2 and the Sources notes card in P04.6):
// the textarea starts from the saved notes, Save keeps them and toasts.
export function EditNotesDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const notes = useOwnerNotes();
  const save = useSaveOwnerNotes();
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setText(notes.data?.text ?? "");
      setError(null);
    }
  }, [open, notes.data?.text]);

  function saveNotes(): void {
    setError(null);
    save.mutate(text, {
      onSuccess: () => {
        toast("Saved. Charie reads your notes in the next learning run.");
        onOpenChange(false);
      },
      onError: (saveError) => {
        setError(saveError.message);
        toast("Couldn't save your notes. Try again.");
      },
    });
  }

  const fileRef = useRef<HTMLInputElement>(null);

  async function loadFromFile(file: File | undefined): Promise<void> {
    if (!file) return;
    setText(await file.text());
    if (fileRef.current) fileRef.current.value = '';
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>Your notes</DialogTitle>
        <DialogDescription>
          Write the rules of your business, one per line, like &ldquo;Never convert
          currencies.&rdquo; Charie sorts them into hard rules, style rules and hints
          when it learns.
        </DialogDescription>
        {notes.isPending ? (
          <p className="mt-4 text-[14px] text-muted" role="status">
            Loading your notes…
          </p>
        ) : (
          <Textarea
            aria-label="Your notes"
            rows={14}
            className="mt-4"
            value={text}
            onChange={(event) => setText(event.target.value)}
          />
        )}
        {error !== null && (
          <p role="alert" className="mt-2.5 text-[13.5px] font-medium text-bad-ink">
            {error}
          </p>
        )}
        <DialogFooter className="flex-wrap">
          <input
            ref={fileRef}
            type="file"
            accept=".md,.txt"
            className="sr-only" tabIndex={-1}
            aria-label="Load notes from a file"
            onChange={(event) => void loadFromFile(event.target.files?.[0])}
          />
          <Button variant="ghost" onClick={() => fileRef.current?.click()}>
            Load from a file
          </Button>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button disabled={notes.isPending || save.isPending} onClick={saveNotes}>
            {save.isPending ? "Saving…" : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
