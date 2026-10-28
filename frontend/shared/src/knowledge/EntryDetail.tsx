import { Check, FileText } from "lucide-react";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { ConfidencePill, kindLabel } from "./KnowledgeList";
import type { KnowledgeEntry } from "./types";

// One entry's evidence: meanings, how it is worked out, recipe tests,
// sources with quotes and history. Read-only here: no Edit, Approve or
// Mark as wrong controls (the learner editor adds them in P04.8).
export function EntryDetail({
  entry,
  version,
  onSuggest,
}: {
  entry: KnowledgeEntry;
  version: number | null;
  onSuggest: () => void;
}) {
  return (
    <Card padded aria-label={entry.name}>
      <div className="flex flex-wrap items-center gap-2">
        <ConfidencePill confidence={entry.confidence} />
        <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-transparent px-2.5 text-[12.5px] font-medium text-text-2">
          {kindLabel(entry.kind)}
        </span>
        {version !== null && (
          <span className="ml-auto text-[12.5px] text-muted">Version {version}</span>
        )}
      </div>
      <h2 className="mt-2.5 font-serif text-[22px] font-semibold leading-[1.3]">{entry.name}</h2>
      <p className="mt-1.5 text-[14.5px]">{entry.meaning ?? entry.short}</p>
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
            {entry.sources.map((source) => (
              <li
                key={source.doc}
                className="flex gap-2.5 rounded-[12px] bg-surface-2 p-[10px_12px]"
              >
                <FileText aria-hidden="true" className="mt-0.5 flex-none text-muted [--icon:16px]" />
                <div>
                  <div className="text-[13.5px] font-medium">{source.doc}</div>
                  {source.quote && (
                    <blockquote className="mt-0.5 border-l-2 border-border pl-2 text-[13.5px] text-text-2">
                      “{source.quote}”
                    </blockquote>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
      {entry.history && entry.history.length > 0 && (
        <div className="mt-4">
          <div className="text-[12.5px] font-semibold uppercase tracking-wide text-muted">
            History
          </div>
          <ul className="mt-1.5 grid gap-1 text-[13.5px] text-text-2">
            {entry.history.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      )}
      <div className="mt-4 flex items-center gap-2 border-t border-border pt-3.5">
        <span className="text-[12.5px] text-muted">Used in {entry.used} answers</span>
        <Button variant="outline" size="sm" className="ml-auto" onClick={onSuggest}>
          Suggest a change
        </Button>
      </div>
    </Card>
  );
}
