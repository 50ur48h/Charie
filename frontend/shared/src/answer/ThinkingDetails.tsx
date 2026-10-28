// The expandable evidence inside one thinking line. Everything renders as
// plain React text (never raw HTML): SQL stays selectable text, source names
// and quotes stay inert text.
import type { ThinkingLine } from "./thinking";

export function ThinkingDetails({
  line,
  omitExplanation = false,
}: {
  line: ThinkingLine;
  omitExplanation?: boolean;
}) {
  const details = line.details;
  return (
    <div className="mt-1 space-y-2 text-[13.5px]">
      {!omitExplanation && line.body !== undefined && line.body !== "" && (
        <p className="m-0 text-text-2">{line.body}</p>
      )}
      {details?.sql !== undefined && (
        <div>
          <div className="mb-1 text-[12px] font-medium tracking-wide text-muted uppercase">
            Query
          </div>
          <pre className="m-0 overflow-x-auto rounded-[9px] bg-surface-2 p-3 font-mono text-[12.5px] break-all whitespace-pre-wrap select-text">
            <code>{details.sql}</code>
          </pre>
        </div>
      )}
      {details?.document !== undefined && (
        <div className="rounded-[9px] bg-surface-2 p-3">
          <div className="font-medium">{details.document}</div>
          {details.quote !== undefined && (
            <p className="m-0 mt-1 text-text-2">&ldquo;{details.quote}&rdquo;</p>
          )}
          {details.location !== undefined && (
            <div className="mt-1 text-[12.5px] text-muted">{details.location}</div>
          )}
        </div>
      )}
      {!omitExplanation && details?.note !== undefined && (
        <p className="m-0 text-text-2">{details.note}</p>
      )}
    </div>
  );
}
