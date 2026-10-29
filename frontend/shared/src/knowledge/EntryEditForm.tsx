import { useState } from "react";
import { Button } from "../components/Button";
import { Field, Input } from "../components/Input";
import { Textarea } from "../components/Textarea";

// Edit an entry's title and meaning inside its card (P04.8). Recipes stay
// read-only: code tests them, so nobody types them by hand.
export function EntryEditForm({
  title,
  meaning,
  saving = false,
  serverError = null,
  onSave,
  onCancel,
}: {
  title: string;
  meaning: string;
  saving?: boolean;
  serverError?: string | null;
  onSave: (patch: { title: string; meaning: string }) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState(title);
  const [text, setText] = useState(meaning);
  const [blank, setBlank] = useState(false);
  const error = blank ? "The entry still needs a title and a meaning." : serverError;
  return (
    <form
      className="mt-2.5"
      onSubmit={(event) => {
        event.preventDefault();
        if (name.trim() === "" || text.trim() === "") {
          setBlank(true);
          return;
        }
        onSave({ title: name.trim(), meaning: text.trim() });
      }}
    >
      <Field label="Title" htmlFor="knowledge-edit-title">
        <Input
          id="knowledge-edit-title"
          value={name}
          onChange={(event) => {
            setName(event.target.value);
            setBlank(false);
          }}
          aria-invalid={error ? true : undefined}
        />
      </Field>
      <Field label="Meaning" htmlFor="knowledge-edit-meaning">
        <Textarea
          id="knowledge-edit-meaning"
          rows={4}
          value={text}
          onChange={(event) => {
            setText(event.target.value);
            setBlank(false);
          }}
          aria-invalid={error ? true : undefined}
        />
      </Field>
      {error && (
        <p role="alert" className="mt-2 text-[12.5px] text-bad-ink">
          {error}
        </p>
      )}
      <p className="mt-2 text-[12.5px] text-muted">
        Saving marks it as confirmed by you, in the draft version.
      </p>
      <div className="mt-3 flex justify-end gap-2">
        <Button variant="ghost" type="button" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" disabled={saving}>
          {saving ? "Saving…" : "Save change"}
        </Button>
      </div>
    </form>
  );
}
