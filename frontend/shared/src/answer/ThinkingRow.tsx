import {
  Check,
  ChevronDown,
  FileText,
  Lightbulb,
  Search,
  Sparkles,
  StickyNote,
  ListOrdered,
  X,
} from "lucide-react";
import { Spinner } from "../components/Spinner";
import { cn } from "../components/cn";
import type { ThinkingKind, ThinkingLine } from "./thinking";
import { ThinkingDetails } from "./ThinkingDetails";

const KIND_ICONS = {
  step: ListOrdered,
  found: Sparkles,
  query: Search,
  document: FileText,
  decision: Lightbulb,
  check: Check,
  note: StickyNote,
} as const satisfies Record<ThinkingKind, typeof Search>;

export function ThinkingRow({
  line,
  expanded,
  onToggle,
  idPrefix,
}: {
  line: ThinkingLine;
  expanded: boolean;
  onToggle: () => void;
  idPrefix: string;
}) {
  const Icon = KIND_ICONS[line.kind];
  const regionId = `${idPrefix}-line-${line.seq}`;
  const failed = line.status === "failed";
  return (
    <div>
      <button
        type="button"
        aria-expanded={expanded}
        aria-controls={regionId}
        onClick={onToggle}
        className={cn(
          "flex w-full cursor-pointer items-center gap-2 rounded-[10px] px-2 py-[7px] text-left text-[14px] transition-colors duration-200",
          failed ? "text-bad-ink hover:bg-bad-soft" : "text-text-2 hover:bg-surface-2",
        )}
      >
        {line.status === "running" ? (
          <Spinner />
        ) : failed ? (
          <X size={15} aria-hidden="true" className="flex-none" />
        ) : (
          <Icon size={15} aria-hidden="true" className="flex-none text-muted" />
        )}
        <span className="min-w-0 flex-1 truncate">{line.title}</span>
        <ChevronDown
          size={15}
          aria-hidden="true"
          className={cn("flex-none text-muted transition-transform duration-200", expanded && "rotate-180")}
        />
      </button>
      {expanded && (
        <div id={regionId} role="region" className="px-2 pt-1 pb-2 pl-[37px]">
          {failed && (line.body ?? line.details?.note) !== undefined && (
            <p className="m-0 mb-2 text-[13.5px] text-bad-ink">
              {line.body ?? line.details?.note}
            </p>
          )}
          <ThinkingDetails line={line} omitExplanation={failed} />
        </div>
      )}
    </div>
  );
}
