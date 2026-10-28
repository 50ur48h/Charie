// The thinking panel: a live, plain-English timeline while the answer runs,
// and a collapsed one-line summary once it is done. Expansion is local
// state set once per answer, so a refresh never collapses what the reader
// opened. Progress announces politely (architecture 09).
import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { Spinner } from "../components/Spinner";
import { cn } from "../components/cn";
import { formatSummary, type ThinkingLine, type ThinkingSummary } from "./thinking";
import { ThinkingRow } from "./ThinkingRow";

export function ThinkingPanel({
  lines,
  summary,
  panelId,
}: {
  lines: ThinkingLine[];
  summary: ThinkingSummary | null;
  panelId: string;
}) {
  const running = lines.some((line) => line.status === "running");
  // Open while running or failed, collapsed once done. Failed rows start
  // expanded too, so the explanation is visible. Never re-derived, so user
  // expansion holds.
  const [expanded, setExpanded] = useState(
    () => running || lines.some((line) => line.status === "failed"),
  );
  const [openRows, setOpenRows] = useState<ReadonlySet<number>>(
    () => new Set(lines.filter((line) => line.status === "failed").map((line) => line.seq)),
  );
  if (lines.length === 0) return null;

  const heading = summary !== null ? formatSummary(summary) : running ? "Thinking…" : "Thinking";

  function toggleRow(seq: number): void {
    setOpenRows((prev) => {
      const next = new Set(prev);
      if (next.has(seq)) {
        next.delete(seq);
      } else {
        next.add(seq);
      }
      return next;
    });
  }

  return (
    <div className="mb-1" aria-live={running ? "polite" : undefined}>
      <button
        type="button"
        aria-expanded={expanded}
        aria-controls={`${panelId}-timeline`}
        onClick={() => setExpanded((was) => !was)}
        className="flex max-w-full cursor-pointer items-center gap-2 rounded-full bg-surface-2 py-[7px] pr-[14px] pl-[10px] text-left text-[14px] transition-colors duration-200 hover:bg-surface-2/70"
      >
        {running && <Spinner />}
        <span className="min-w-0 flex-1 truncate font-normal text-text-2">{heading}</span>
        <ChevronDown
          size={15}
          aria-hidden="true"
          className={cn("flex-none text-muted transition-transform duration-200", expanded && "rotate-180")}
        />
      </button>
      {expanded && (
        <div id={`${panelId}-timeline`} role="region" className="pt-1">
          {lines.map((line) => (
            <ThinkingRow
              key={line.seq}
              line={line}
              idPrefix={panelId}
              expanded={openRows.has(line.seq)}
              onToggle={() => toggleRow(line.seq)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
