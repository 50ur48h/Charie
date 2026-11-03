"use client";

/**
 * The organization's own documents (plan WP10.1b, architecture 5.5).
 *
 * The screen adds no behaviour. Everything it shows is a row the API already
 * returns, which is what architecture 3.1 means by a deliberately thin
 * frontend. Three rules shape it rather than decorate it.
 *
 *   1. **A Reader is not shown controls they cannot use** (B-008). Uploading,
 *      re-indexing and deleting are Contributor-or-Admin; the API refuses and
 *      audits them anyway, and offering the button teaches people the product
 *      is broken rather than that they lack permission. Unknown role fails
 *      closed, which costs a Contributor one page load.
 *   2. **A part-indexed document says so in words.** `embedded_count` below
 *      `chunk_count` means the text is searchable by wording but not yet by
 *      meaning — a real and temporary state the API reports deliberately, and
 *      rounding it up to "indexed" would hide the one thing somebody waiting on
 *      a large upload wants to know.
 *   3. **A failure is rendered as the thing to act on**, not as another line of
 *      metadata. `failure_reason` is written for whoever uploaded the file — a
 *      scanned PDF says it needs OCR — so it is shown as-is rather than
 *      replaced with a generic message.
 */

import { BookOpen, CircleAlert, FileText, FileUp, RotateCw, Trash2, Upload, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Badge, type Tone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { SkeletonList } from "@/components/ui/skeleton";
import { Hint } from "@/components/ui/tooltip";
import { createApi, type KnowledgeDocument } from "@/lib/api-client";
import { useSession } from "@/lib/auth/session";
import { cn } from "@/lib/utils";

/** What the API's `extract` module accepts. Mirrored for the file picker only. */
const ACCEPT = ".md,.markdown,.txt,.text,.pdf";

const STATUS_TONES: Record<string, Tone> = {
  indexed: "mint",
  failed: "rose",
  pending: "peach",
};

const KINDS: Record<string, string> = {
  "text/markdown": "Markdown",
  "text/plain": "Plain text",
  "application/pdf": "PDF",
};

/**
 * How much of a document is searchable, in words.
 *
 * Deliberately three outcomes rather than two. "Indexed" alone would claim a
 * document is fully searchable when its vectors have not arrived, and that is
 * the state a large upload spends the longest in.
 */
export function indexingSummary(document: KnowledgeDocument): string {
  if (document.status === "failed") {
    return document.chunk_count > 0
      ? `${document.chunk_count} passages stored, searchable by wording only`
      : "Nothing was indexed";
  }
  if (document.chunk_count === 0) return "Not indexed yet";
  if (document.embedded_count >= document.chunk_count) {
    return `${document.chunk_count} passages, searchable by wording and meaning`;
  }
  return (
    `${document.chunk_count} passages, ` +
    `${document.embedded_count} searchable by meaning so far`
  );
}

/**
 * How far through indexing a document is, or `null` when there is no honest
 * fraction to draw.
 *
 * **A meter needs two real numbers** (docs/design.md). Before any passage is
 * stored the denominator does not exist, so there is nothing to draw and the
 * words carry it instead — a bar at 0% would be claiming a total nobody knows.
 * A failed document gets no meter either: it is not part-way anywhere, it has
 * stopped.
 */
function indexedFraction(document: KnowledgeDocument): number | null {
  if (document.status === "failed" || document.chunk_count === 0) return null;
  return Math.min(1, document.embedded_count / document.chunk_count);
}

/** When a document arrived, as a date. The API's own string if it is not one. */
function added(timestamp: string): string {
  const parsed = new Date(timestamp);
  return Number.isNaN(parsed.getTime())
    ? timestamp
    : parsed.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function size(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function Documents({ orgId, role }: { orgId: string; role: string | null }) {
  const session = useSession();
  const api = useMemo(() => createApi(session.getToken), [session.getToken]);

  // Uploading a document changes what every future run is told a term means, so
  // it is Contributor-or-Admin (architecture 10.2). Unknown role fails closed.
  const canWrite = role === "admin" || role === "contributor";

  const [documents, setDocuments] = useState<KnowledgeDocument[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [title, setTitle] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement | null>(null);

  const load = useCallback(async () => {
    setDocuments(await api.documents(orgId));
  }, [api, orgId]);

  useEffect(() => {
    // Guarded so a slow response cannot write into an unmounted screen.
    let active = true;
    void (async () => {
      try {
        const next = await api.documents(orgId);
        if (active) setDocuments(next);
      } catch (cause) {
        if (active) setError(cause instanceof Error ? cause.message : "Could not load");
      }
    })();
    return () => {
      active = false;
    };
  }, [api, orgId]);

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "That did not work");
    } finally {
      setBusy(false);
    }
  };

  const clearFile = () => {
    setFile(null);
    if (fileInput.current) fileInput.current.value = "";
  };

  const upload = async () => {
    if (!file) return;
    await run(async () => {
      await api.uploadDocument(orgId, file, title);
      // Cleared inside the action, so it only happens on success: a failed
      // upload leaves the chosen file in place and the person can retry without
      // finding it again.
      setFile(null);
      setTitle("");
      if (fileInput.current) fileInput.current.value = "";
    });
  };

  const failure = (message: string) => (
    <div className="flex animate-fade-up items-start gap-3 rounded-md bg-bad-soft px-4 py-3 text-[13.5px] text-bad-ink">
      <CircleAlert aria-hidden="true" className="mt-[3px] size-4 shrink-0" />
      <p role="alert" className="min-w-0 [overflow-wrap:anywhere]">
        {message}
      </p>
    </div>
  );

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-5">
      {canWrite ? (
        <Card
          title="Add a document"
          subtitle="Markdown, plain text, or a PDF with a text layer. Scanned pages need OCR first."
        >
          <div className="grid grid-cols-[minmax(0,1fr)] gap-4">
            <label
              className={cn(
                "relative flex cursor-pointer items-center gap-4 rounded-lg border border-dashed px-4 py-4 transition-colors has-[input:focus-visible]:border-brand has-[input:focus-visible]:ring-[3px] has-[input:focus-visible]:ring-brand-soft sm:px-5",
                dragging
                  ? "border-brand bg-brand-soft/50"
                  : "border-faint bg-surface-2/40 hover:border-brand hover:bg-brand-soft/25",
              )}
              onDragOver={(event) => {
                event.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(event) => {
                event.preventDefault();
                setDragging(false);
                const dropped = event.dataTransfer.files[0];
                if (dropped) setFile(dropped);
              }}
            >
              <input
                ref={fileInput}
                className="sr-only"
                type="file"
                accept={ACCEPT}
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              />
              <span
                aria-hidden="true"
                className="grid size-11 shrink-0 place-items-center rounded-full bg-brand-soft text-brand-ink [&_svg]:size-5"
              >
                <FileUp />
              </span>
              <span className="grid min-w-0 flex-1 gap-0.5">
                <span className="text-[14px] font-medium text-text">
                  {file ? "Drop another file, or choose a different one" : "Drop a file here, or choose one"}
                </span>
                <span className="text-[12.5px] text-muted-foreground">.md, .txt or .pdf</span>
              </span>
              <span
                aria-hidden="true"
                className="hidden h-8 shrink-0 items-center rounded-sm border border-border bg-surface px-3 text-[13px] font-medium text-text shadow-[0_1px_2px_rgba(var(--shadow-rgb),.05)] sm:inline-flex"
              >
                {file ? "Change file" : "Choose file"}
              </span>
            </label>

            {file && (
              <div className="flex animate-fade-up items-center gap-3 rounded-md border border-border-soft bg-surface px-3 py-2.5">
                <FileText aria-hidden="true" className="size-4 shrink-0 text-brand-ink" />
                <span className="min-w-0 flex-1 truncate text-[13.5px] font-medium text-text">
                  {file.name}
                </span>
                <span className="shrink-0 text-[12.5px] text-muted-foreground tabular-nums">
                  {size(file.size)}
                </span>
                <Hint label="Clear the chosen file">
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label="Clear the chosen file"
                    disabled={busy}
                    onClick={clearFile}
                  >
                    <X />
                  </Button>
                </Hint>
              </div>
            )}

            <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
              <div className="min-w-0 flex-1">
                <Input
                  label="Title (optional)"
                  value={title}
                  placeholder="Defaults to the file name"
                  onChange={(event) => setTitle(event.target.value)}
                />
              </div>
              <Button
                variant="primary"
                className="h-10 sm:px-5"
                onClick={() => void upload()}
                disabled={busy || !file}
              >
                <Upload />
                {busy ? "Working…" : "Upload"}
              </Button>
            </div>
            {error ? failure(error) : null}
          </div>
        </Card>
      ) : null}

      <Card
        title="Documents"
        subtitle="What this organization has written down. The agent reads these to learn what a term means here."
      >
        {documents === null ? (
          <SkeletonList rows={2} avatar label="Loading documents" />
        ) : documents.length === 0 ? (
          <EmptyState
            icon={<BookOpen />}
            title="No documents yet"
            action={canWrite ? undefined : <span>A Contributor or Admin can add one.</span>}
          >
            {canWrite
              ? "Upload a policy or a definition and the agent will use it."
              : "Policies, definitions and notes this organization writes down will appear here."}
          </EmptyState>
        ) : (
          <ul className="-mx-2 grid">
            {documents.map((document, index) => {
              const fraction = indexedFraction(document);
              return (
                <li
                  key={document.id}
                  className="flex animate-fade-up items-start gap-3.5 border-b border-border-soft px-2 py-4 first:pt-1 last:border-b-0 last:pb-1"
                  style={{ animationDelay: `${index * 40}ms` }}
                >
                  <span
                    aria-hidden="true"
                    className={cn(
                      "grid size-10 shrink-0 place-items-center rounded-md [&_svg]:size-[18px]",
                      document.status === "failed"
                        ? "bg-bad-soft text-bad-ink"
                        : "bg-brand-soft text-brand-ink",
                    )}
                  >
                    <FileText />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                          <h3 className="text-[14.5px] leading-snug font-semibold text-text [overflow-wrap:anywhere]">
                            {document.title}
                          </h3>
                          <Badge tone={STATUS_TONES[document.status] ?? "neutral"}>
                            {document.status}
                          </Badge>
                        </div>
                        <p className="mt-1 text-[13px] text-text-2">{indexingSummary(document)}</p>
                        <p className="mt-0.5 text-[12px] text-muted-foreground">
                          {KINDS[document.mime] ?? document.mime} · Added {added(document.created_at)}
                        </p>
                      </div>
                      {canWrite ? (
                        <div className="-mr-1 flex shrink-0 items-center gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() =>
                              void run(async () => {
                                await api.reindexDocument(orgId, document.id);
                              })
                            }
                            disabled={busy}
                          >
                            <RotateCw />
                            Re-index
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="hover:bg-bad-soft hover:text-bad-ink"
                            onClick={() =>
                              void run(async () => {
                                await api.removeDocument(orgId, document.id);
                              })
                            }
                            disabled={busy}
                          >
                            <Trash2 />
                            Remove
                          </Button>
                        </div>
                      ) : null}
                    </div>

                    {/* Drawn only from `chunk_count` and `embedded_count`, and
                        only when both exist. The words above say the same thing
                        and are what a reader with no colour or no meter gets. */}
                    {fraction !== null && (
                      <span
                        className="mt-2.5 block h-1.5 max-w-[320px] overflow-hidden rounded-full bg-surface-2"
                        role="progressbar"
                        aria-valuemin={0}
                        aria-valuemax={document.chunk_count}
                        aria-valuenow={document.embedded_count}
                        aria-label={`${document.title}: passages searchable by meaning`}
                      >
                        <span
                          className="block h-full rounded-full bg-brand transition-[width] duration-500 ease-out"
                          style={{ width: `${fraction * 100}%` }}
                        />
                      </span>
                    )}

                    {/* The one thing on this row a person has to act on, so it
                        is not styled as another line of metadata. */}
                    {document.failure_reason ? (
                      <div className="mt-3 flex items-start gap-2.5 rounded-md bg-bad-soft/60 px-3.5 py-2.5 text-[13px] leading-relaxed text-text-2">
                        <CircleAlert aria-hidden="true" className="mt-[3px] size-4 shrink-0 text-bad-ink" />
                        <p className="min-w-0 [overflow-wrap:anywhere]">{document.failure_reason}</p>
                      </div>
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
        {!canWrite && error ? <div className="mt-4">{failure(error)}</div> : null}
      </Card>
    </div>
  );
}
