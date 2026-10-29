import { Check, CircleAlert } from "lucide-react";
import { Pill, Progress, Spinner, type LearnerDocument } from "@charie/shared";

// One Documents table status cell (P04.5): the pill or reader for each
// document state, in the design's words.
export function DocumentStatus({ document }: { document: LearnerDocument }) {
  if (document.status === "new") {
    return <Pill tone="accent">New · not learned yet</Pill>;
  }
  if (document.status === "reading") {
    return (
      <span className="flex min-w-[150px] items-center gap-2">
        <Spinner label="Reading" />
        <Progress value={document.progress ?? 0} max={100} label="Reading progress" thin className="flex-1" />
        <span className="text-[12.5px] text-muted">Reading</span>
      </span>
    );
  }
  if (document.status === "failed") {
    return (
      <span title={document.error ?? undefined}>
        <Pill tone="bad" icon={CircleAlert}>
          Couldn&apos;t read it
        </Pill>
      </span>
    );
  }
  if (document.unreadable_pages > 0) {
    const pages =
      document.unreadable_pages === 1
        ? "1 page unreadable"
        : `${document.unreadable_pages} pages unreadable`;
    return (
      <Pill tone="bad" icon={CircleAlert}>
        {pages}
      </Pill>
    );
  }
  const facts = document.fact_count === 1 ? "1 fact" : `${document.fact_count} facts`;
  return (
    <Pill tone="good" icon={Check}>
      Learned · {facts}
    </Pill>
  );
}
