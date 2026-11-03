"use client";

/**
 * The query behind an answer, as a person may check it (plan WP7.3, B-034).
 *
 * This is the screen that makes the product's central claim checkable. An answer
 * says "128 orders"; a finding points at the execution that produced it; this
 * opens that execution and shows the statement, the rows it returned and how
 * long it took.
 *
 * Three things it will not blur together:
 *
 * **A refusal is not an empty result.** A statement the DAL declined to send
 * reached no engine, so it has no rows — it shows its violation code and the
 * statement that earned it instead of an empty table.
 *
 * **A preview is not the result.** The table shows at most the rows the
 * artifact keeps inline, so "50 shown of 71,798" is said in those words.
 *
 * **A masked column is labelled where it is read.** The values arrive already
 * masked — there is no unmasked copy (D-013, WP5.2b) — so the header carries
 * the badge.
 *
 * The SQL and the cells are shown verbatim: somebody asking why the answer looks
 * odd should be able to read exactly what ran and exactly what came back.
 */

import { CircleSlash, Clock, Database, Rows3, TriangleAlert } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import { DataTable } from "@/components/answer/data-table";
import { SqlBlock } from "@/components/answer/sql-block";
import { Badge } from "@/components/ui/badge";
import { ApiError, createApi, type Execution } from "@/lib/api-client";
import { useSession } from "@/lib/auth/session";

/** What a cell shows when the database returned no value at all. */
const NOTHING = "—";

function cell(value: unknown): string {
  if (value === null || value === undefined) return NOTHING;
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}

function duration(ms: number | null): string | null {
  if (ms === null) return null;
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

/** "50 shown of 71,798" rather than a table the reader has to measure. */
function rowSummary(execution: Execution): string {
  const total = execution.row_count;
  const shown = execution.sample_rows.length;
  if (total === null) return `${shown} row${shown === 1 ? "" : "s"}`;
  const counted = total.toLocaleString();
  if (shown >= total) return `${counted} row${total === 1 ? "" : "s"}`;
  return `${shown} shown of ${counted}`;
}

function Fact({ icon, children }: { icon: ReactNode; children: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 [&_svg]:size-3.5 [&_svg]:text-faint">
      {icon}
      <span>{children}</span>
    </span>
  );
}

function Refused({ execution }: { execution: Execution }) {
  return (
    <div className="grid gap-1.5 rounded-md bg-bad-soft px-3 py-2.5">
      <div className="flex flex-wrap items-center gap-2">
        <CircleSlash aria-hidden="true" className="size-4 text-bad" />
        <Badge tone="rose">refused</Badge>
        {execution.violation_code && <Badge tone="neutral">{execution.violation_code}</Badge>}
      </div>
      <p className="text-[13.5px] text-bad-ink">
        {execution.error ?? "This statement was refused before it reached the database."}
      </p>
      <p className="text-[12.5px] text-muted-foreground">
        Nothing was sent to the database, so there are no rows to show.
      </p>
    </div>
  );
}

function Failed({ execution }: { execution: Execution }) {
  return (
    <div className="grid gap-1.5 rounded-md bg-warn-soft px-3 py-2.5">
      <div className="flex items-center gap-2">
        <TriangleAlert aria-hidden="true" className="size-4 text-warn" />
        <Badge tone="peach">error</Badge>
      </div>
      <p className="text-[13.5px] text-warn-ink">
        {execution.error ?? "The database did not answer this statement."}
      </p>
    </div>
  );
}

function Results({ execution }: { execution: Execution }) {
  const masked = useMemo(() => new Set(execution.masked_columns), [execution.masked_columns]);
  const columns = useMemo(
    () =>
      execution.columns.map((name) => ({
        label: name,
        ...(masked.has(name) ? { badge: <Badge tone="peach" className="ml-1.5">masked</Badge> } : {}),
      })),
    [execution.columns, masked],
  );
  const rows = useMemo(
    () => execution.sample_rows.map((row) => execution.columns.map((_, position) => cell(row[position]))),
    [execution.sample_rows, execution.columns],
  );

  if (execution.columns.length === 0) {
    return <p className="text-[13px] text-muted-foreground">This query returned no columns.</p>;
  }
  return (
    <>
      {rows.length > 0 && (
        <div className="rounded-md border border-border bg-surface px-2">
          <DataTable columns={columns} rows={rows} maxHeight={320} caption="Rows the query returned" />
        </div>
      )}
      {rows.length === 0 && <p className="text-[13px] text-muted-foreground">This query matched no rows.</p>}
      {execution.masked_columns.length > 0 && (
        <p className="text-[12.5px] text-muted-foreground">
          Values in masked columns were obscured by an organization policy before they were stored.
          The unmasked values were never kept.
        </p>
      )}
    </>
  );
}

export function EvidencePanel({
  orgId,
  runId,
  executionId,
}: {
  orgId: string;
  runId: string;
  executionId: string;
}) {
  const session = useSession();
  const [execution, setExecution] = useState<Execution | null>(null);
  const [error, setError] = useState<string | null>(null);
  const api = useMemo(() => createApi(session.getToken), [session.getToken]);

  useEffect(() => {
    // Guarded so a slow response cannot write into an unmounted panel — a
    // citation can be collapsed again before the query comes back.
    let active = true;
    void (async () => {
      try {
        const found = await api.execution(orgId, runId, executionId);
        if (active) setExecution(found);
      } catch (cause) {
        // A citation that will not open is said out loud rather than rendered
        // as an empty panel, which would look like the evidence being thin.
        if (active) {
          setError(cause instanceof ApiError ? cause.message : "This citation could not be opened.");
        }
      }
    })();
    return () => {
      active = false;
    };
  }, [api, orgId, runId, executionId]);

  if (error) return <p className="text-[13px] text-bad-ink">{error}</p>;
  if (!execution) {
    return (
      <p className="flex items-center gap-2 text-[13px] text-muted-foreground">
        <span aria-hidden="true" className="size-3 animate-spin rounded-full border-2 border-brand-soft border-t-brand" />
        Opening the query…
      </p>
    );
  }

  const took = duration(execution.duration_ms);
  return (
    <div className="grid min-w-0 animate-fade-up grid-cols-[minmax(0,1fr)] gap-2.5 rounded-md border border-border-soft bg-background/70 p-3">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12.5px] text-muted-foreground">
        {execution.status === "ok" && <Fact icon={<Rows3 aria-hidden="true" />}>{rowSummary(execution)}</Fact>}
        {took && <Fact icon={<Clock aria-hidden="true" />}>{took}</Fact>}
        {execution.tables.length > 0 && (
          <Fact icon={<Database aria-hidden="true" />}>{execution.tables.join(", ")}</Fact>
        )}
        {execution.truncated && <Badge tone="peach">truncated</Badge>}
        {execution.sensitive_accessed && <Badge tone="lilac">touched sensitive columns</Badge>}
      </div>

      <SqlBlock sql={execution.sql} />

      {execution.status === "refused" && <Refused execution={execution} />}
      {execution.status === "error" && <Failed execution={execution} />}
      {execution.status === "ok" && <Results execution={execution} />}
    </div>
  );
}
