import { Check, FileText, SquarePen } from "lucide-react";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { detailLines } from "./detailLines";
import { entryGroupLabel } from "./groups";
import { ConfidencePill } from "./KnowledgeList";
import type { KnowledgeEntry, KnowledgeHistoryItem, KnowledgeSource } from "./types";
import { EntryEditForm } from "./EntryEditForm";

const SOURCE_LABEL: Record<string, string> = {
  structure: "Read from the database structure",
  profile: "Measured from the data",
  query: "Tested with a query",
  owner_notes: "From your notes",
  owner_edit: "Edited by you",
  owner_approval: "Approved by you",
  ai_explanation: "Explained by Charie from the data and your notes",
};

function sourceLabel(source: KnowledgeSource): string {
  if (source.type !== undefined && SOURCE_LABEL[source.type] !== undefined) {
    return SOURCE_LABEL[source.type];
  }
  return source.text ?? source.doc ?? source.type ?? "A source";
}

// One entry's evidence: details, meanings, how it is worked out, recipe
// tests, sources with quotes, and history. Read-only shows "Suggest a
// change"; the learner editor adds Edit, Mark as wrong and Approve (P04.8).
export function EntryDetail({
  entry,
  version,
  history,
  editable = false,
  editing = false,
  savingEdit = false,
  editError = null,
  approving = false,
  onSuggest,
  onStartEdit,
  onCancelEdit,
  onSaveEdit,
  onApprove,
  onWrong,
}: {
  entry: KnowledgeEntry;
  version: { number: number; status: string } | number | null;
  history: KnowledgeHistoryItem[];
  editable?: boolean;
  editing?: boolean;
  savingEdit?: boolean;
  editError?: string | null;
  approving?: boolean;
  onSuggest: () => void;
  onStartEdit?: () => void;
  onCancelEdit?: () => void;
  onSaveEdit?: (patch: { title: string; meaning: string }) => void;
  onApprove?: () => void;
  onWrong?: () => void;
}) {
  const confirmed = entry.confidence === "confirmed";
  const details = detailLines(entry.kind, entry.details);
  return (
    <Card padded aria-label={entry.title}>
      <div className="flex flex-wrap items-center gap-2">
        <ConfidencePill confidence={entry.confidence} />
        <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-transparent px-2.5 text-[12.5px] font-medium text-text-2">
          {entryGroupLabel(entry.kind)}
        </span>
        {version !== null && (
          <span className="ml-auto text-[12.5px] text-muted">{versionLabel(version)}</span>
        )}
      </div>
      {editing && editable ? (
        <EntryEditForm
          title={entry.title}
          meaning={entry.meaning}
          saving={savingEdit}
          serverError={editError}
          onSave={(patch) => onSaveEdit?.(patch)}
          onCancel={() => onCancelEdit?.()}
        />
      ) : (
        <>
          <h2 className="mt-2.5 font-serif text-[22px] font-semibold leading-[1.3]">{entry.title}</h2>
          <p className="mt-1.5 text-[14.5px]">{entry.meaning}</p>
        </>
      )}
      {details.length > 0 && (
        <div className="mt-4">
          <div className="text-[12.5px] font-semibold uppercase tracking-wide text-muted">
            Details
          </div>
          <ul className="mt-1.5 grid gap-1 text-[14px]">
            {details.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
      )}
      {entry.how && entry.how.length > 0 && (
        <div className="mt-4">
          <div className="text-[12.5px] font-semibold uppercase tracking-wide text-muted">
            How it&apos;s worked out
          </div>
          <ol className="mt-1.5 grid list-decimal gap-1 pl-5 text-[14px]">
            {entry.how.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
          {entry.sql && (
            <details className="mt-2">
              <summary className="cursor-pointer text-[13.5px] font-medium text-accent-ink">
                Show the query
              </summary>
              <pre className="mt-1.5 overflow-x-auto rounded-[10px] bg-code-bg p-3 font-mono text-[12.5px] text-code-ink">
                {entry.sql}
              </pre>
            </details>
          )}
        </div>
      )}
      {entry.checks && entry.checks.length > 0 && (
        <div className="mt-4">
          <div className="text-[12.5px] font-semibold uppercase tracking-wide text-muted">
            Checked against the data
          </div>
          <ul className="mt-1.5 grid gap-1.5">
            {entry.checks.map((check) => (
              <li key={check} className="flex items-start gap-2 text-[14px]">
                <Check aria-hidden="true" className="mt-0.5 flex-none text-good-ink [--icon:15px]" />
                {check}
              </li>
            ))}
          </ul>
        </div>
      )}
      {entry.sources && entry.sources.length > 0 && (
        <div className="mt-4">
          <div className="text-[12.5px] font-semibold uppercase tracking-wide text-muted">
            Where it came from
          </div>
          <ul className="mt-1.5 grid gap-2">
            {entry.sources.map((source, index) => (
              <li
                key={`${sourceLabel(source)}-${index}`}
                className="flex gap-2.5 rounded-[12px] bg-surface-2 p-[10px_12px]"
              >
                <FileText aria-hidden="true" className="mt-0.5 flex-none text-muted [--icon:16px]" />
                <div>
                  <div className="text-[13.5px] font-medium">{sourceLabel(source)}</div>
                  {source.quote && (
                    <blockquote className="mt-0.5 border-l-2 border-border pl-2 text-[13.5px] text-text-2">
                      “{source.quote}”
                    </blockquote>
                  )}
                  {source.sql && (
                    <details className="mt-1">
                      <summary className="cursor-pointer text-[13px] font-medium text-accent-ink">
                        Show the query
                      </summary>
                      <pre className="mt-1 overflow-x-auto rounded-[8px] bg-code-bg p-2 font-mono text-[12px] text-code-ink">
                        {source.sql}
                      </pre>
                    </details>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
      {history.length > 0 && (
        <div className="mt-4">
          <div className="text-[12.5px] font-semibold uppercase tracking-wide text-muted">
            History
          </div>
          <ul className="mt-1.5 grid gap-1 text-[13.5px] text-text-2">
            {history.map((item, index) => (
              <li key={`${item.version}-${item.change}-${index}`}>
                Version {item.version} · {item.reason === "" ? item.change : item.reason}
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-border pt-3.5">
        {entry.used !== undefined && (
          <span className="text-[12.5px] text-muted">Used in {entry.used} answers</span>
        )}
        {editable ? (
          <span className="ml-auto inline-flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={() => onStartEdit?.()}>
              <SquarePen aria-hidden="true" className="[--icon:15px]" />
              Edit
            </Button>
            <Button variant="danger" size="sm" onClick={() => onWrong?.()}>
              Mark as wrong
            </Button>
            <Button
              size="sm"
              disabled={confirmed || approving}
              title={confirmed ? "Already confirmed by you" : undefined}
              onClick={() => onApprove?.()}
            >
              <Check aria-hidden="true" className="[--icon:15px]" />
              {approving ? "Approving…" : "Approve"}
            </Button>
          </span>
        ) : (
          <Button variant="outline" size="sm" className="ml-auto" onClick={onSuggest}>
            Suggest a change
          </Button>
        )}
      </div>
    </Card>
  );
}

function versionLabel(version: { number: number; status: string } | number): string {
  if (typeof version === "number") return `Version ${version}`;
  return version.status === "draft" ? `Draft version ${version.number}` : `Version ${version.number}`;
}
