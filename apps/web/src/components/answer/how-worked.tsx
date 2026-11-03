"use client";

/**
 * "How I worked this out" (design: `.a-sources`): the method, the definitions,
 * the findings and the queries behind them, and what it cost.
 *
 * **A citation opens.** Each finding lists the executions behind it, and each
 * one expands into the statement that ran and the rows it returned — the
 * product's central claim made checkable rather than asserted. A finding with a
 * single citation shows its query outright once the panel is open (D-047).
 *
 * The body stays mounted while closed (it only collapses), so opening it never
 * waits on a fetch it could have started earlier.
 */

import { ChevronDown, ChevronRight, ListChecks } from "lucide-react";
import { useState, type ReactNode } from "react";

import { EvidencePanel } from "@/components/screens/evidence";
import type { Finding, Run } from "@/lib/api-client";
import { cn } from "@/lib/utils";

const CONFIDENCE_TONES: Record<string, string> = {
  high: "bg-good-soft text-good-ink",
  medium: "bg-brand-soft text-brand-ink",
  low: "bg-warn-soft text-warn-ink",
};

function Citation({
  orgId,
  runId,
  executionId,
  label,
  startOpen,
}: {
  orgId: string;
  runId: string;
  executionId: string;
  label: string;
  startOpen: boolean;
}) {
  const [open, setOpen] = useState(startOpen);
  return (
    <div className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-2">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((was) => !was)}
        className="inline-flex w-fit items-center gap-1 rounded-sm text-[13px] font-medium text-brand-ink transition-colors hover:text-text"
      >
        <ChevronRight
          aria-hidden="true"
          className={cn("size-3.5 transition-transform duration-200", open && "rotate-90")}
        />
        {open ? "Hide" : "Show"} {label}
      </button>
      {open && <EvidencePanel orgId={orgId} runId={runId} executionId={executionId} />}
    </div>
  );
}

/**
 * The claims behind the reply, and the queries behind those.
 *
 * A single-shot run writes one finding whose statement *is* the answer, so the
 * statement is not repeated then. Cited findings are the evidence for this
 * answer; the rest are the investigation's working and live in the trace.
 */
function Findings({
  orgId,
  runId,
  findings,
  answer,
}: {
  orgId: string;
  runId: string;
  findings: Finding[];
  answer: string | null;
}) {
  const anyCited = findings.some((finding) => finding.cited);
  const shown = anyCited ? findings.filter((finding) => finding.cited) : findings;
  if (shown.length === 0) return null;
  return (
    <ul className="grid grid-cols-[minmax(0,1fr)] gap-2.5">
      {shown.map((finding) => (
        <li key={finding.id} className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-2 rounded-md bg-surface-2 px-3 py-2.5">
          <span
            className={cn(
              "w-fit rounded-full px-2 py-0.5 text-[11px] font-semibold",
              CONFIDENCE_TONES[finding.confidence] ?? "bg-surface text-text-2",
            )}
          >
            {finding.confidence} confidence
          </span>
          {finding.statement.trim() !== (answer ?? "").trim() && (
            <p className="text-[13.5px] leading-relaxed text-text-2">{finding.statement}</p>
          )}
          {finding.support.length === 0 ? (
            <p className="text-[13px] text-muted-foreground">This claim cites no query.</p>
          ) : (
            finding.support.map((executionId, position) => (
              <Citation
                key={executionId}
                orgId={orgId}
                runId={runId}
                executionId={executionId}
                startOpen={finding.support.length === 1}
                label={
                  finding.support.length === 1
                    ? "the query behind this"
                    : `query ${position + 1} of ${finding.support.length}`
                }
              />
            ))
          )}
        </li>
      ))}
    </ul>
  );
}

/**
 * What this organization's own definitions did to this answer (B-087).
 *
 * Silent when there was nothing to match; said when definitions existed and
 * the question reached none of them — the state nobody could otherwise see.
 */
export function groundingLine(run: Run): string | null {
  const applied = run.definitions_applied ?? [];
  const available = run.definitions_available ?? 0;
  if (applied.length > 0) return `governed by ${applied.join(", ")}`;
  if (available > 0) return `no definition matched this question (${available} defined here)`;
  return null;
}

/**
 * What the question cost, beside the working that produced it.
 *
 * **Null means unpriced, never free**: a run holding a call the price table
 * does not cover reports no total rather than one that quietly omits it, and a
 * sub-cent run never reads as "$0.0000".
 */
export function Cost({ run }: { run: Run }) {
  const usage = run.model_usage ?? {};
  const calls = usage.calls ?? 0;
  if (calls === 0 && run.cost_estimate == null) return null;

  const unpriced = usage.unpriced_calls ?? 0;
  const total = run.cost_estimate == null ? null : Number(run.cost_estimate);
  const money =
    total === null
      ? null
      : total === 0
        ? "less than $0.0001"
        : `$${total.toFixed(total < 0.01 ? 4 : 2)}`;
  const estimated = usage.estimated_calls ?? 0;
  const cached = usage.cached_input_tokens;

  const detail = [
    `${calls} model call${calls === 1 ? "" : "s"}`,
    usage.input_tokens || usage.output_tokens
      ? `${((usage.input_tokens ?? 0) + (usage.output_tokens ?? 0)).toLocaleString()} tokens`
      : null,
    // The provider bills cached input at less than the rate this figure used.
    cached ? `${cached.toLocaleString()} cached` : null,
    estimated > 0 ? `${estimated} estimated` : null,
    unpriced > 0 ? `${unpriced} not priced` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <span className="flex flex-wrap items-baseline gap-x-2" data-testid="run-cost">
      <span className="font-semibold text-text tabular-nums">{money ?? "not priced"}</span>
      <span className="text-muted-foreground">{detail}</span>
    </span>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-1 gap-1 text-[13.5px] sm:grid-cols-[96px_minmax(0,1fr)] sm:gap-3">
      <div className="pt-0.5 text-[12.5px] font-semibold text-muted-foreground">{label}</div>
      <div className="min-w-0 leading-relaxed text-text-2">{children}</div>
    </div>
  );
}

export function HowIWorked({
  orgId,
  run,
  answer,
}: {
  orgId: string;
  run: Run;
  answer: string | null;
}) {
  const [open, setOpen] = useState(false);
  const queries = run.findings.reduce((total, finding) => total + finding.support.length, 0);
  const grounding = groundingLine(run);
  const hasFindings = run.findings.length > 0;
  const costShown =
    (run.model_usage?.calls ?? 0) > 0 || run.cost_estimate !== null && run.cost_estimate !== undefined;

  if (!hasFindings && !run.method && !grounding && !costShown) return null;

  return (
    <div className="animate-fade-up overflow-hidden rounded-lg border border-border bg-surface font-sans">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((was) => !was)}
        className="flex w-full items-center gap-2.5 px-4 py-3 text-left transition-colors hover:bg-surface-2/50"
      >
        <ListChecks aria-hidden="true" className="size-[18px] shrink-0 text-brand" />
        <span className="shrink-0 text-[14px] font-semibold text-text">How I worked this out</span>
        <span className="min-w-0 truncate text-[13px] text-muted-foreground">
          {hasFindings ? (
            <>
              <span>Evidence</span> · {queries} quer{queries === 1 ? "y" : "ies"}
              {run.method ? " · method" : ""}
            </>
          ) : (
            "Method and cost"
          )}
        </span>
        <ChevronDown
          aria-hidden="true"
          className={cn(
            "ml-auto size-4 shrink-0 text-muted-foreground transition-transform duration-300",
            open && "rotate-180",
          )}
        />
      </button>
      <div
        className={cn(
          "grid transition-[grid-template-rows] duration-400 ease-[cubic-bezier(.2,.8,.2,1)]",
          open ? "grid-rows-[1fr]" : "grid-rows-[0fr]",
        )}
      >
        <div className={cn("min-h-0 overflow-hidden", !open && "invisible")}>
          <div className="grid grid-cols-[minmax(0,1fr)] gap-3.5 px-4 pt-1 pb-4">
            {run.method && <Row label="Method">{run.method}</Row>}
            {grounding && <Row label="Definitions">{grounding}</Row>}
            {hasFindings && (
              <Row label="Findings">
                <Findings orgId={orgId} runId={run.id} findings={run.findings} answer={answer} />
              </Row>
            )}
            {costShown && (
              <Row label="Cost">
                <Cost run={run} />
              </Row>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
