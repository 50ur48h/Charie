import { useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { FileText, Trash2 } from "lucide-react";
import {
  Button,
  Card,
  ConfirmDialog,
  DataTable,
  Dropzone,
  IconButton,
  Progress,
  toast,
  uploadDocument,
  useDocuments,
  useRemoveDocument,
  useRetryDocument,
  type LearnerDocument,
} from "@charie/shared";
import { useQueryClient } from "@tanstack/react-query";
import { checkFile } from "./fileRules";
import { dayOrDate } from "../lib/when";
import { DocumentStatus } from "./DocumentStatus";

// The Sources documents section (P04.5): dropzone with upload progress,
// the table with every status, Remove (with a confirm), Retry and Show all.
// In mock mode an upload moves from New to Reading to Learned.
export function DocumentsCard() {
  const client = useQueryClient();
  const documents = useDocuments();
  const remove = useRemoveDocument();
  const retry = useRetryDocument();
  const [uploads, setUploads] = useState<{ key: string; name: string; progress: number }[]>([]);
  const [expanded, setExpanded] = useState(false);
  const [removing, setRemoving] = useState<LearnerDocument | null>(null);

  function drop(files: File[]): void {
    for (const file of files) {
      const bad = checkFile(file);
      if (bad !== null) {
        toast(bad);
        continue;
      }
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
          toast(error instanceof Error ? error.message : "Couldn't add that file.");
        },
      );
    }
  }

  if (documents.isPending) {
    return (
      <Card padded={false} className="p-[20px_22px]">
        <p className="text-[14px] text-muted" role="status">
          Loading documents…
        </p>
      </Card>
    );
  }
  if (documents.isError || !documents.data) {
    return (
      <Card padded={false} className="p-[20px_22px]">
        <p className="text-[14px] text-muted" role="alert">
          Couldn&rsquo;t load the documents.{" "}
          <button
            type="button"
            className="font-medium text-accent-ink underline-offset-2 hover:underline"
            onClick={() => void documents.refetch()}
          >
            Try again
          </button>
        </p>
      </Card>
    );
  }

  const list = documents.data.documents;
  const pages = list.reduce((sum, doc) => sum + (doc.pages ?? 0), 0);
  const shown = expanded ? list : list.slice(0, 7);

  const columns: ColumnDef<LearnerDocument>[] = [
    {
      id: "document",
      header: "Document",
      cell: ({ row }) => (
        <span className="flex items-center gap-2.5 font-medium">
          <FileText aria-hidden="true" className="flex-none text-muted [--icon:17px]" />
          {row.original.file_name}
        </span>
      ),
    },
    {
      id: "pages",
      header: "Pages",
      cell: ({ row }) => (row.original.pages === null ? "—" : String(row.original.pages)),
    },
    {
      id: "added",
      header: "Added",
      cell: ({ row }) => dayOrDate(row.original.uploaded_at),
    },
    {
      id: "status",
      header: "Status",
      cell: ({ row }) => <DocumentStatus document={row.original} />,
    },
    {
      id: "actions",
      header: "",
      cell: ({ row }) => (
        <RowAction
          document={row.original}
          retrying={retry.isPending}
          onRetry={() =>
            retry.mutate(row.original.id, {
              onSuccess: () => toast("Reading it again."),
              onError: (error) => toast(error.message),
            })
          }
          onRemove={() => setRemoving(row.original)}
        />
      ),
    },
  ];

  return (
    <Card padded={false} className="p-4">
      <Dropzone
        onFiles={drop}
        title="Drop files here, or click to choose"
        hint="Word, PDF, PowerPoint, Excel, Markdown or text. Up to 50 MB each."
      />
      {uploads.map((upload) => (
        <p
          key={upload.key}
          className="mt-3 flex items-center gap-2.5 text-[14px]"
          role="status"
          aria-label={`Adding ${upload.name}, ${upload.progress} percent`}
        >
          <FileText aria-hidden="true" className="flex-none text-muted [--icon:17px]" />
          <span className="min-w-0 flex-1 truncate font-medium">{upload.name}</span>
          <Progress value={upload.progress} max={100} label="Upload progress" thin className="w-28 flex-none" />
          <span className="flex-none tabular-nums text-muted">{upload.progress}%</span>
        </p>
      ))}
      <div className="mt-3">
        {list.length === 0 && uploads.length === 0 ? (
          <p className="py-2 text-[14px] text-muted">No documents yet. Drop files here to start.</p>
        ) : (
          <>
            <DataTable columns={columns} data={shown} caption="Documents" />
            {list.length > 7 && (
              <p className="mt-2.5 text-center">
                <Button variant="ghost" size="sm" onClick={() => setExpanded(!expanded)}>
                  {expanded ? "Show fewer" : `Show all ${list.length} documents`}
                </Button>
              </p>
            )}
            <p className="sr-only" role="status">
              {list.length} documents · {pages} pages
            </p>
          </>
        )}
      </div>
      <ConfirmDialog
        open={removing !== null}
        onOpenChange={(open) => {
          if (!open) setRemoving(null);
        }}
        title={removing !== null ? `Remove ${removing.file_name}?` : "Remove this document?"}
        body="Charie stops using it. Facts that only came from this document get marked to check."
        confirmLabel="Remove"
        tone="danger"
        onConfirm={() => {
          if (!removing) return;
          const name = removing.file_name;
          remove.mutate(removing.id, {
            onSuccess: () => {
              setRemoving(null);
              toast(`Removed ${name}.`);
            },
            onError: (error) => toast(error.message),
          });
        }}
      />
    </Card>
  );
}

function RowAction({
  document,
  retrying,
  onRetry,
  onRemove,
}: {
  document: LearnerDocument;
  retrying: boolean;
  onRetry: () => void;
  onRemove: () => void;
}) {
  if (document.status === "reading") return null;
  if (document.status === "failed" || document.unreadable_pages > 0) {
    return (
      <Button variant="outline" size="sm" disabled={retrying} onClick={onRetry}>
        Retry
      </Button>
    );
  }
  return (
    <IconButton label="Remove" onClick={onRemove}>
      <Trash2 aria-hidden="true" />
    </IconButton>
  );
}
