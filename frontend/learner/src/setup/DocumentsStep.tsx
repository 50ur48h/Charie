import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Check, CircleAlert, FileText, NotebookPen } from "lucide-react";
import {
  Button,
  Dropzone,
  Pill,
  Spinner,
  formatBytes,
  uploadDocument,
  useDocuments,
  useOwnerNotes,
  type LearnerDocument,
} from "@charie/shared";
import { checkFile } from "../sources/fileRules";
import { EditNotesDialog } from "../sources/EditNotesDialog";

// Step 2: documents and notes. Dropped files upload with progress (XHR);
// the row shows "Adding…" then "Added". A bad file shows the plain-English
// message in the red box. The notes row opens the editor dialog and stays
// visible when documents fail to load (their API comes in Phase 8).
export function DocumentsStep({ onBack, onNext }: { onBack: () => void; onNext: () => void }) {
  const client = useQueryClient();
  const documents = useDocuments();
  const notes = useOwnerNotes();
  const [uploads, setUploads] = useState<{ key: string; name: string; progress: number }[]>([]);
  const [errors, setErrors] = useState<string[]>([]);
  const [editingNotes, setEditingNotes] = useState(false);

  function drop(files: File[]): void {
    const bad = files.map(checkFile).filter((message): message is string => message !== null);
    const good = files.filter((file) => checkFile(file) === null);
    setErrors(bad);
    for (const file of good) {
      const key = `${file.name}:${file.size}:${Date.now()}:${Math.random()}`;
      setUploads((current) => [...current, { key, name: file.name, progress: 0 }]);
      void uploadDocument(file, (progress) =>
        setUploads((current) =>
          current.map((upload) => (upload.key === key ? { ...upload, progress } : upload)),
        ),
      ).then(
        () => {
          setUploads((current) => current.filter((upload) => upload.key !== key));
          void client.invalidateQueries({ queryKey: ["learner-documents"] });
          void client.invalidateQueries({ queryKey: ["learner-setup"] });
        },
        (error: unknown) => {
          setUploads((current) => current.filter((upload) => upload.key !== key));
          setErrors((current) => [
            ...current,
            error instanceof Error ? error.message : "Couldn't add that file.",
          ]);
        },
      );
    }
  }

  const list = documents.data?.documents ?? [];
  const saved = (notes.data?.text ?? "").trim() !== "";

  return (
    <section aria-label="Add documents and notes">
      <h2 className="font-serif text-[24px] font-semibold">Add documents and notes</h2>
      <p className="mt-1.5 text-[14.5px] text-muted">
        Anything that explains your business: definitions, policies, menus, promotions,
        incident logs. Your own notes tell Charie the rules, like &ldquo;never convert
        currencies&rdquo;.
      </p>
      <div className="mt-5">
        <Dropzone
          onFiles={drop}
          title="Drop files here, or click to choose"
          hint="Word, PDF, PowerPoint, Excel, Markdown or text"
        />
      </div>
      {errors.length > 0 && (
        <div role="alert" className="mt-3.5 grid gap-1.5 rounded-[14px] border border-bad bg-bad-soft p-[14px_16px] text-[14px] font-medium text-bad-ink">
          {errors.map((message) => (
            <p key={message} className="flex items-start gap-2">
              <CircleAlert aria-hidden="true" className="mt-px flex-none [--icon:17px]" />
              {message}
            </p>
          ))}
        </div>
      )}
      {documents.isPending ? (
        <p className="mt-3.5 text-[14px] text-muted" role="status">
          Loading your documents…
        </p>
      ) : documents.isError ? (
        <p className="mt-3.5 text-[14px] text-muted" role="alert">
          Couldn&rsquo;t load your documents.{" "}
          <button
            type="button"
            className="font-medium text-accent-ink underline-offset-2 hover:underline"
            onClick={() => void documents.refetch()}
          >
            Try again
          </button>
        </p>
      ) : null}
      <ul className="mt-3.5 grid max-h-[280px] gap-2 overflow-y-auto" aria-label="Your documents">
          {uploads.map((upload) => (
            <li
              key={upload.key}
              className="flex items-center gap-3 rounded-[12px] bg-surface-2 p-[10px_14px] text-[14px]"
            >
              <FileText aria-hidden="true" className="flex-none text-muted [--icon:17px]" />
              <span className="min-w-0 flex-1 truncate font-medium">{upload.name}</span>
              <span className="flex flex-none items-center gap-2 text-[13px] text-muted">
                <Spinner label={`Adding ${upload.name}`} />
                Adding…{upload.progress > 0 ? ` ${upload.progress}%` : ""}
              </span>
            </li>
          ))}
          {list.map((doc) => (
            <DocumentRow key={doc.id} doc={doc} />
          ))}
          <li className="flex items-center gap-3 rounded-[12px] bg-surface-2 p-[10px_14px] text-[14px]">
            <NotebookPen aria-hidden="true" className="flex-none text-muted [--icon:17px]" />
            <span className="min-w-0 flex-1 truncate font-medium">Owner notes.md</span>
            <span className="flex-none text-[12.5px] text-muted">Your rules</span>
            {saved ? (
              <>
                <Pill tone="accent" icon={Check}>
                  Notes added
                </Pill>
                <Button variant="ghost" size="sm" className="flex-none" onClick={() => setEditingNotes(true)}>
                  Edit notes
                </Button>
              </>
            ) : (
              <Button variant="outline" size="sm" className="ml-auto flex-none" onClick={() => setEditingNotes(true)}>
                Add notes
              </Button>
            )}
          </li>
      </ul>
      <div className="mt-6 flex flex-wrap gap-2.5 border-t border-border-soft pt-[18px]">
        <Button variant="ghost" onClick={onBack}>
          <ArrowLeft aria-hidden="true" className="[--icon:16px]" />
          Back
        </Button>
        <Button className="ml-auto max-[640px]:ml-0 max-[640px]:w-full" onClick={onNext}>
          Continue
          <ArrowRight aria-hidden="true" className="[--icon:16px]" />
        </Button>
      </div>
      <EditNotesDialog open={editingNotes} onOpenChange={setEditingNotes} />
    </section>
  );
}

function DocumentRow({ doc }: { doc: LearnerDocument }) {
  const sub =
    doc.pages !== null && doc.pages !== undefined
      ? `${doc.pages} pages`
      : formatBytes(doc.size_bytes);
  return (
    <li className="flex items-center gap-3 rounded-[12px] bg-surface-2 p-[10px_14px] text-[14px]">
      <FileText aria-hidden="true" className="flex-none text-muted [--icon:17px]" />
      <span className="min-w-0 flex-1 truncate font-medium">{doc.file_name}</span>
      <span className="flex-none text-[12.5px] text-muted">{sub}</span>
      <Pill tone="good" icon={Check}>
        Added
      </Pill>
    </li>
  );
}
