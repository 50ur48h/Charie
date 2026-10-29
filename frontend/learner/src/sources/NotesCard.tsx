import { useState } from "react";
import { Lightbulb, MessageSquare, NotebookPen, ShieldCheck } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import {
  Button,
  Card,
  IconBox,
  useOwnerNotes,
  type SortedNotes,
} from "@charie/shared";
import { shortDate } from "../lib/when";
import { EditNotesDialog } from "./EditNotesDialog";

// The "Your notes" section of Sources (P04.6): the notes, then how Charie
// understood them in three columns, with Edit notes. Changed notes also
// turn on the refresh banner so Charie can learn them.
export function NotesCard() {
  const notes = useOwnerNotes();
  const [editing, setEditing] = useState(false);

  if (notes.isPending) {
    return (
      <Card padded={false} className="p-[20px_22px]">
        <p className="text-[14px] text-muted" role="status">
          Loading your notes…
        </p>
      </Card>
    );
  }
  if (notes.isError || !notes.data) {
    return (
      <Card padded={false} className="p-[20px_22px]">
        <p className="text-[14px] text-muted" role="alert">
          Couldn&rsquo;t load your notes.{" "}
          <button
            type="button"
            className="font-medium text-accent-ink underline-offset-2 hover:underline"
            onClick={() => void notes.refetch()}
          >
            Try again
          </button>
        </p>
      </Card>
    );
  }

  const saved = notes.data;
  const lines = saved.text.split("\n").filter((line) => line.trim() !== "").length;

  return (
    <Card padded={false} className="p-[20px_22px]">
      <div className="flex items-center gap-3">
        <IconBox icon={NotebookPen} tone="plain" />
        <div className="min-w-0 flex-1">
          <b className="text-[16px]">Owner notes.md</b>
          {saved.text.trim() !== "" && saved.saved_at !== null && (
            <p className="text-[12.5px] text-muted">
              Updated {shortDate(saved.saved_at)} · {lines === 1 ? "1 line" : `${lines} lines`}
            </p>
          )}
        </div>
        {saved.text.trim() !== "" ? (
          <Button variant="outline" size="sm" className="ml-auto" onClick={() => setEditing(true)}>
            Edit notes
          </Button>
        ) : (
          <Button variant="outline" size="sm" className="ml-auto" onClick={() => setEditing(true)}>
            Add notes
          </Button>
        )}
      </div>
      {saved.text.trim() === "" ? (
        <p className="mt-3 text-[14px] text-muted">
          No notes yet. Add the rules Charie must follow, like &ldquo;never convert
          currencies&rdquo;.
        </p>
      ) : saved.sorted === null ? (
        <p className="mt-3 text-[14px] text-muted">
          Charie sorts your notes into rules the next time it learns.
        </p>
      ) : (
        <>
          {saved.saved_at !== null &&
            saved.sorted_at !== null &&
            Date.parse(saved.saved_at) > Date.parse(saved.sorted_at) && (
              <p className="mt-3 text-[14px] text-muted">
                You changed your notes. Charie sorts them again when it next learns.
              </p>
            )}
          <div className="mt-3.5 grid gap-3 md:grid-cols-3">
            <NoteColumn
              icon={ShieldCheck}
              heading="Hard rules"
              line="Code enforces these. Charie can't break them."
              rules={saved.sorted.hard_rules}
            />
            <NoteColumn
              icon={MessageSquare}
              heading="Style"
              line="Charie follows these when writing."
              rules={saved.sorted.style_rules}
            />
            <NoteColumn
              icon={Lightbulb}
              heading="Hints about the data"
              line="Added to Charie's knowledge."
              rules={saved.sorted.data_hints}
            />
          </div>
        </>
      )}
      <EditNotesDialog open={editing} onOpenChange={setEditing} />
    </Card>
  );
}

function NoteColumn({
  icon,
  heading,
  line,
  rules,
}: {
  icon: LucideIcon;
  heading: string;
  line: string;
  rules: SortedNotes[keyof SortedNotes];
}) {
  const Icon = icon;
  return (
    <div className="rounded-[14px] bg-surface-2 p-[14px_16px]">
      <h4 className="mb-1 flex items-center gap-2 text-[14px]">
        <Icon aria-hidden="true" className="[--icon:16px]" />
        {heading}
      </h4>
      <p className="mb-2.5 text-[12.5px] text-muted">{line}</p>
      {rules.length === 0 ? (
        <p className="text-[13.5px] text-muted">None yet.</p>
      ) : (
        <ul className="grid gap-1.5 pl-[18px] text-[13.5px]">
          {rules.map((rule) => (
            <li key={rule} className="list-disc">
              {rule}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
