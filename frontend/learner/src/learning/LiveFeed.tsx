import { BadgeCheck, CircleCheck, CircleHelp, Info, TriangleAlert } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Card, useLearningFeed, type LearningEventKind } from "@charie/shared";
import { clockTime } from "../lib/when";

// What Charie is finding (P04.7): the last 7 feed lines, newest at the
// bottom, live in mock mode. Polite so screen readers hear new lines.
export function LiveFeed({ runId, active }: { runId: number | null; active: boolean }) {
  const feed = useLearningFeed(runId, active);
  const lines = feed.lines.slice(-7);
  return (
    <Card padded={false} className="p-[20px_22px]">
      <p className="card-title">What Charie is finding</p>
      <p className="card-sub">Live, in plain words</p>
      {lines.length === 0 ? (
        <p className="mt-3 text-[14px] text-muted">Nothing yet. Lines appear here as Charie works.</p>
      ) : (
        <div className="mt-3 flex max-h-[420px] max-[640px]:max-h-[320px] flex-col justify-end gap-2 overflow-hidden" aria-live="polite">
          {lines.map((line) => (
            <FeedLine key={line.seq} line={line} />
          ))}
        </div>
      )}
    </Card>
  );
}

const LINE_ICONS: Record<LearningEventKind, { icon: LucideIcon; className: string }> = {
  found: { icon: CircleCheck, className: "text-good" },
  info: { icon: Info, className: "text-accent" },
  question: { icon: CircleHelp, className: "text-warn" },
  warning: { icon: TriangleAlert, className: "text-warn" },
  done: { icon: BadgeCheck, className: "text-good" },
};

function FeedLine({ line }: { line: { seq: number; at: string; kind: LearningEventKind; message: string } }) {
  const { icon: Icon, className } = LINE_ICONS[line.kind];
  return (
    <p className="flex items-start gap-2.5 rounded-[12px] bg-surface-2 p-[10px_12px] text-[14px]">
      <Icon aria-hidden="true" className={`mt-0.5 flex-none [--icon:16px] ${className}`} />
      <span>{line.message}</span>
      {line.at !== "" && (
        <time className="ml-auto whitespace-nowrap pl-2.5 text-[12px] tabular-nums text-muted">
          {clockTime(line.at)}
        </time>
      )}
    </p>
  );
}
