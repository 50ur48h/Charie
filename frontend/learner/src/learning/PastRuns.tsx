import type { ColumnDef } from "@tanstack/react-table";
import { DataTable, Pill, StatusDot, type LearningRun } from "@charie/shared";
import { clockTime, dayOrDate, howLong } from "../lib/when";

// Past learning runs (P04.7): when, why, how long, what changed and the
// result for every run, newest first.
export function PastRuns({ runs }: { runs: LearningRun[] }) {
  const columns: ColumnDef<LearningRun>[] = [
    {
      id: "when",
      header: "When",
      cell: ({ row }) => `${dayOrDate(row.original.started_at)}, ${clockTime(row.original.started_at)}`,
    },
    {
      id: "why",
      header: "Why",
      cell: ({ row }) => runWhy(row.original),
    },
    {
      id: "took",
      header: "Took",
      cell: ({ row }) => {
        if (row.original.status === "running") return <span className="text-muted">Running</span>;
        if (row.original.status === "paused") return <span className="text-muted">Paused</span>;
        return row.original.finished_at !== null
          ? howLong(row.original.started_at, row.original.finished_at)
          : "—";
      },
    },
    {
      id: "changed",
      header: "What changed",
      cell: ({ row }) =>
        row.original.status === "running"
          ? `So far: ${row.original.summary ?? "nothing yet"}`
          : (row.original.summary ?? "—"),
    },
    {
      id: "result",
      header: "Result",
      cell: ({ row }) => <RunResult run={row.original} />,
    },
  ];
  return <DataTable columns={columns} data={runs} caption="Past learning runs" />;
}

function runWhy(run: LearningRun): string {
  if (run.kind === "first") return "First learning";
  if (run.kind === "nightly") return "Nightly check";
  return `Refresh: ${run.reason ?? "changes"}`;
}

function RunResult({ run }: { run: LearningRun }) {
  if (run.status === "running") {
    return (
      <Pill tone="good">
        <StatusDot tone="good" />
        Draft version {run.version_number}
      </Pill>
    );
  }
  if (run.status === "paused") return <Pill tone="warn">Paused</Pill>;
  if (run.status === "failed") return <Pill tone="bad">Didn&apos;t finish</Pill>;
  return run.new_version ? (
    <Pill tone="accent">Version {run.version_number}</Pill>
  ) : (
    <Pill tone="neutral">Version {run.version_number} kept</Pill>
  );
}
