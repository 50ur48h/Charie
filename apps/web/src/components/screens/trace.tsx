"use client";

/** How the answer was reached, as it is reached (plan WP8.3, architecture 10.3). */

import { ChevronDown, Sparkles } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { createApi, type RunEvent } from "@/lib/api-client";
import { useSession } from "@/lib/auth/session";
import { modelName } from "@/lib/models";
import { cn } from "@/lib/utils";

/** What each step did, and where it matters, why. */
type Payload = Record<string, unknown>;

interface Step {
  lead: string;
  rest: string;
}

function str(payload: Payload, key: string): string | null {
  const value = payload[key];
  return typeof value === "string" && value.length > 0 ? value : null;
}

function num(payload: Payload, key: string): number | null {
  const value = payload[key];
  return typeof value === "number" ? value : null;
}

function list(payload: Payload, key: string): string[] {
  const value = payload[key];
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function totalsOf(payload: Payload): Payload {
  const value = payload.totals;
  return typeof value === "object" && value !== null ? (value as Payload) : {};
}

/** A nested object, or null. `null` is a value a payload deliberately carries. */
function nested(payload: Payload, key: string): Payload | null {
  const value = payload[key];
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Payload)
    : null;
}

/** "1 row" / "3 rows", so no sentence ever says "1 rows". */
function plural(count: number, one: string, many: string): string {
  return `${count.toLocaleString()} ${count === 1 ? one : many}`;
}

/** What each model role did, for the live model-call rows. */
const ROLE_DOING: Record<string, string> = {
  intake: "read the question",
  observe: "read the results",
  plan: "planned the checks",
  sql: "wrote the query",
  critic: "reviewed the answer",
  compose: "wrote the answer",
  embed: "embedded the text",
};

function joinNames(names: string[], limit = 3): string {
  const shown = names.slice(0, limit).join(", ");
  return names.length > limit ? `${shown} and ${names.length - limit} more` : shown;
}

export const STEP_SENTENCES: Record<string, (payload: Payload) => Step> = {
  run_started: () => ({ lead: "Picked up the question", rest: "" }),

  intent_classified: () => ({
    lead: "Worked out what kind of question this is",
    rest: "so the right steps get chosen.",
  }),

  context_selected: (payload) => {
    // This builder spends what the event already carries (WP13.21).
    const tables = list(payload, "tables");
    const definitions = list(payload, "definitions_applied");
    const available = num(payload, "definitions_available");
    const inFull = num(payload, "tables_in_full");
    const inOutline = num(payload, "tables_in_outline");
    const dropped = num(payload, "tables_dropped");
    const sentences: string[] = [];

    if (tables.length > 0) {
      // B-160. How much of each the model actually saw, not just how many the search returned.
      const detail =
        inFull !== null && inOutline !== null && inOutline > 0
          ? ` — ${inFull} in full and ${inOutline} in outline`
          : "";
      sentences.push(
        `and picked ${plural(tables.length, "table", "tables")}${detail}: ${joinNames(tables)}.`,
      );
    }
    if (dropped !== null && dropped > 0) {
      sentences.push(
        `${plural(dropped, "table", "tables")} matched but would not fit the prompt, so ${dropped === 1 ? "it was" : "they were"} left out.`,
      );
    }
    if (str(payload, "tables_found_via") === "thread") {
      sentences.push("The question named no table of its own, so the earlier turns chose them.");
    }
    const byMeaning = Object.values(nested(payload, "tables_found_by") ?? {}).filter(
      (arm) => arm === "vector" || arm === "both",
    ).length;
    if (byMeaning > 0 && tables.length > 0) {
      sentences.push(
        `${byMeaning} of them ${byMeaning === 1 ? "was" : "were"} found by meaning rather than by matching a word.`,
      );
    }
    if (available !== null && available > 0) {
      // B-087's finding, said out loud.
      sentences.push(
        definitions.length > 0
          ? `${definitions.length} of your ${available} definitions applied: ${joinNames(definitions, 2)}.`
          : `None of your ${available} definitions matched this question.`,
      );
    }
    const restricted = num(payload, "restrictions");
    if (restricted !== null && restricted > 0) {
      sentences.push(`${plural(restricted, "column is", "columns are")} restricted by policy.`);
    }
    const turns = num(payload, "history_turns");
    if (turns !== null && turns > 0) {
      sentences.push(`Read with ${plural(turns, "earlier turn", "earlier turns")} for context.`);
    }
    return {
      lead: "Searched the catalogue for tables that fit the question",
      rest: sentences.join(" "),
    };
  },

  capability_checked: (payload) => {
    const unreachable = list(payload, "unreachable");
    const comparable = list(payload, "comparable");
    const period = str(payload, "available_period");
    const blocked = unreachable.length > 0 ? joinNames(unreachable) : null;
    const sentences: string[] = [];

    if (payload.answerable === false) {
      sentences.push(
        blocked
          ? `— they cannot (${blocked}), and joining them anyway would invent rows rather than fail.`
          : "— they cannot, and joining them anyway would invent rows rather than fail.",
      );
    } else {
      sentences.push("— they can, so the numbers will line up row for row.");
      // What it ruled out, which the payload has always carried and the sentence never spent.
      if (blocked) {
        sentences.push(`Ruled out joining ${blocked}: the catalogue records no link.`);
      }
    }
    if (comparable.length > 0) {
      sentences.push(
        `${joinNames(comparable, 2)} can only be compared side by side, not joined row to row.`,
      );
    }
    // Present even when null, which is how an abstention is told apart from a pass (B-157, D-059).
    if ("available_period" in payload) {
      sentences.push(
        period
          ? `The dated columns here run ${period}.`
          : "No dated column here has been profiled, so nothing was compared against.",
      );
    }
    return { lead: "Checked those tables can actually be linked", rest: sentences.join(" ") };
  },

  plan_created: (payload) => {
    const purpose = str(payload, "purpose");
    return {
      lead: "Decided what to look up",
      rest: purpose ? `— ${purpose}.` : "",
    };
  },

  step_started: (payload) => {
    const iteration = num(payload, "iteration");
    return {
      lead: "Started another round of work",
      rest: iteration === null ? "" : `— step ${iteration}.`,
    };
  },

  tool_called: () => ({ lead: "Reached for a tool", rest: "" }),

  knowledge_consulted: (payload) => {
    const term = str(payload, "term");
    const passages = num(payload, "passages");
    const parts = [
      term ? `to see what "${term}" means here` : null,
      passages === null ? null : `found ${plural(passages, "passage", "passages")}`,
    ].filter((part): part is string => part !== null);
    // Empty means empty, not a full stop.
    return {
      lead: "Looked the wording up in your own documents",
      rest: parts.length > 0 ? `${parts.join(", ")}.` : "",
    };
  },

  sql_validated: () => ({
    lead: "Checked the query was safe to run",
    rest: "before sending it to the database.",
  }),

  sql_rejected: (payload) => {
    const rule = str(payload, "rule");
    return {
      lead: "Refused the query before it ran",
      rest: rule ? `— ${rule}. It was rewritten rather than sent.` : "and rewrote it instead.",
    };
  },

  query_executed: (payload) => {
    const rows = num(payload, "row_count");
    const ms = num(payload, "duration_ms");
    const masked = list(payload, "masked_columns");
    const parts: string[] = [];
    if (rows !== null) parts.push(`${plural(rows, "row", "rows")} came back`);
    if (ms !== null) parts.push(`in ${ms.toLocaleString()} ms`);
    if (masked.length > 0) {
      parts.push(`with ${plural(masked.length, "column", "columns")} hidden by policy`);
    }
    return {
      lead: "Ran the query against your database",
      rest: parts.length > 0 ? `— ${parts.join(" ")}.` : "",
    };
  },

  result_summarized: (payload) => {
    const line = str(payload, "one_liner");
    return { lead: "Read what came back", rest: line ? `— ${line}` : "" };
  },

  finding_added: (payload) => {
    const statement = str(payload, "statement");
    const support = list(payload, "support");
    const backed = support.length > 0 ? ` Backed by ${plural(support.length, "query", "queries")}.` : "";
    return {
      lead: "Wrote down a conclusion",
      rest: statement ? `— ${statement}${backed}` : backed.trim(),
    };
  },

  hypothesis_updated: () => ({
    lead: "Changed its mind about what to expect",
    rest: "based on what the last query showed.",
  }),

  reflection: (payload) => {
    const rationale = str(payload, "public_rationale");
    const keepGoing = payload.continue === true;
    return {
      lead: keepGoing ? "Decided to keep looking" : "Decided it had enough to answer",
      rest: rationale ? `— ${rationale}` : "",
    };
  },

  critic_verdict: (payload) => {
    const verdict = str(payload, "verdict");
    const said: Record<string, string> = {
      pass: "— it holds up.",
      revise: "— it overstated something, so it was sent back.",
      insufficient_evidence: "— there was not enough evidence behind it.",
    };
    return {
      lead: "Checked the draft answer against the evidence",
      rest: verdict ? (said[verdict] ?? `— ${verdict}.`) : "",
    };
  },

  budget_warning: (payload) => {
    const dimension = str(payload, "dimension");
    return {
      lead: "Getting close to a limit",
      rest: dimension ? `— ${dimension} for this question.` : "set for this question.",
    };
  },

  budget_exhausted: (payload) => {
    const dimension = str(payload, "dimension");
    const reason = str(payload, "reason");
    return {
      lead: "Stopped at a limit",
      rest: `— ${reason ?? dimension ?? "this question's ceiling"}. The answer says what it did not reach.`,
    };
  },

  answer_composed: (payload) => {
    const limitations = num(payload, "limitations");
    const caveats =
      limitations && limitations > 0
        ? ` with ${plural(limitations, "caveat", "caveats")} attached`
        : "";
    const parts = [`from what the queries returned${caveats}.`];
    // The period check says which of three things happened, including that it could not look.
    const coverage = nested(payload, "coverage");
    if (coverage) {
      const answered = str(coverage, "answered");
      const available = str(coverage, "available");
      const reason = str(coverage, "reason");
      const status = str(coverage, "status");
      if (status === "outside" && answered && available) {
        parts.push(`It covers ${answered}, while the catalogue records ${available}.`);
      } else if (status === "contained" && answered) {
        parts.push(`It covers ${answered}, which is inside the period the catalogue records.`);
      } else if (status === "abstained") {
        parts.push(
          reason
            ? `The period could not be checked: ${reason}.`
            : "The period could not be checked.",
        );
      }
    }
    return { lead: "Wrote the answer", rest: parts.join(" ") };
  },

  run_finished: (payload) => {
    const totals = totalsOf(payload);
    const queries = num(totals, "queries");
    const calls = num(totals, "llm_calls");
    const parts: string[] = [];
    if (queries !== null) parts.push(plural(queries, "query", "queries"));
    if (calls !== null) parts.push(plural(calls, "model call", "model calls"));
    return {
      lead: "Finished",
      rest: parts.length > 0 ? `after ${parts.join(" and ")}.` : "",
    };
  },

  model_called: (payload) => {
    const model = str(payload, "model") ?? "a Meta model";
    const name = modelName(model);
    const role = str(payload, "role");
    const latency = num(payload, "latency_ms");
    const tokensIn = num(payload, "input_tokens");
    const tokensOut = num(payload, "output_tokens");
    if (payload.status === "error") {
      const why = str(payload, "error");
      return {
        lead: `${name} call failed`,
        rest: `Meta Model API (${model})${why ? ` — ${why}` : "."}`,
      };
    }
    const parts = [`Live call to the Meta Model API (${model})`];
    if (latency !== null) parts.push(`${(latency / 1000).toFixed(1)} s`);
    if (tokensIn !== null && tokensOut !== null) {
      parts.push(`${tokensIn.toLocaleString()} tokens in, ${tokensOut.toLocaleString()} out`);
    }
    return {
      lead: `${name} ${(role && ROLE_DOING[role]) ?? "answered"}`,
      rest: `${parts.join(" · ")}.`,
    };
  },

  error: (payload) => {
    const message = str(payload, "safe_message");
    return { lead: "Something went wrong", rest: message ? `— ${message}` : "" };
  },
};

/** The sentence for one event. */
export function sentence(event: RunEvent): Step {
  const build = STEP_SENTENCES[event.type];
  return build ? build(event.payload as Payload) : { lead: event.type, rest: "" };
}

/** Which events are worth colouring, and why — never colour for interest. */
const TONE_CLASS: Record<string, string | undefined> = {
  sql_rejected: "text-warn-ink",
  budget_warning: "text-warn-ink",
  budget_exhausted: "text-warn-ink",
  error: "text-bad-ink",
};

/** Subscribe to a run's trace, replaying whatever came before. */
function useTrace(orgId: string, runId: string | null): RunEvent[] {
  const session = useSession();
  // Keyed by run, so switching runs cannot show the previous one's trace and nothing has to be...
  const [buffer, setBuffer] = useState<{ runId: string | null; events: RunEvent[] }>({
    runId: null,
    events: [],
  });
  const api = useMemo(() => createApi(session.getToken), [session.getToken]);

  useEffect(() => {
    if (!runId) return;
    const controller = new AbortController();
    const seen = new Set<number>();

    void api
      .streamRunEvents(orgId, runId, {
        onEvent: (event) => {
          if (seen.has(event.seq)) return;
          seen.add(event.seq);
          setBuffer((was) =>
            was.runId === runId
              ? { runId, events: [...was.events, event].sort((a, b) => a.seq - b.seq) }
              : { runId, events: [event] },
          );
        },
        signal: controller.signal,
      })
      .catch(() => {
        // A trace that will not load is not worth breaking the answer over.
      });

    return () => controller.abort();
  }, [api, orgId, runId]);

  return buffer.runId === runId ? buffer.events : [];
}


/** How long the run took, in words, from something real. */
function tookFor(
  events: RunEvent[],
  startedAt: string | null | undefined,
  finishedAt: string | null | undefined,
): string {
  const from = startedAt ?? events[0]?.ts;
  const to = finishedAt ?? events.at(-1)?.ts;
  if (!from || !to) return "Thought";

  const ms = new Date(to).getTime() - new Date(from).getTime();
  if (!Number.isFinite(ms) || ms < 0) return "Thought";

  const seconds = Math.max(1, Math.round(ms / 1000));
  if (seconds < 60) return `Thought for ${seconds} second${seconds === 1 ? "" : "s"}`;
  const minutes = Math.round(seconds / 60);
  return `Thought for ${minutes} minute${minutes === 1 ? "" : "s"}`;
}

/** "8 steps", "4 queries", "1 document" — the meta beside the settled pill. */
function metaOf(events: RunEvent[]): string[] {
  const queries = events.filter((event) => event.type === "query_executed").length;
  const documents = events.filter((event) => event.type === "knowledge_consulted").length;
  const calls = events.filter((event) => event.type === "model_called").length;
  return [
    plural(events.length, "step", "steps"),
    calls > 0 ? plural(calls, "Meta model call", "Meta model calls") : null,
    queries > 0 ? plural(queries, "query", "queries") : null,
    documents > 0 ? plural(documents, "document", "documents") : null,
  ].filter((part): part is string => part !== null);
}

/** The working state (docs/design.md, The working state). */
export function Trace({
  orgId,
  runId,
  live,
  defaultOpen = false,
  startedAt,
  finishedAt,
}: {
  orgId: string;
  runId: string | null;
  live: boolean;
  defaultOpen?: boolean;
  /** The run's own clock, for the settled word. Absent falls back to the events. */
  startedAt?: string | null | undefined;
  finishedAt?: string | null | undefined;
}) {
  const events = useTrace(orgId, runId);
  // Open while the run is going and collapsed once it has finished — watching is the point during.
  const [toggled, setToggled] = useState<boolean | null>(null);
  const open = toggled ?? (live || defaultOpen);

  if (!runId || (events.length === 0 && !live)) return null;

  const label = live ? "Thinking" : tookFor(events, startedAt, finishedAt);
  const latest = events.at(-1);
  const now = live && latest ? sentence(latest).lead : null;
  const meta = live ? [] : metaOf(events);

  return (
    <div className="mb-4 font-sans">
      {/* The button's name is the label alone. */}
      <button
        type="button"
        aria-expanded={open}
        aria-label={label}
        onClick={() => setToggled(!open)}
        className="inline-flex max-w-full items-center gap-2 rounded-full bg-surface-2 py-[7px] pr-3.5 pl-2.5 text-[14px] transition-colors hover:bg-head-hover"
      >
        <Sparkles
          aria-hidden="true"
          className={cn("size-[17px] shrink-0 text-brand", live && "animate-breathe")}
        />
        <span
          aria-live="polite"
          className={cn("shrink-0", live ? "text-shimmer font-semibold" : "font-medium text-text-2")}
        >
          {live ? "Thinking…" : label}
        </span>
        {now && (
          <span aria-hidden="true" className="min-w-0 max-w-[380px] truncate text-[13.5px] text-muted-foreground">
            · {now}
          </span>
        )}
        {meta.length > 0 && (
          <span aria-hidden="true" className="hidden items-center gap-1.5 sm:flex">
            {meta.map((part) => (
              <span key={part} className="rounded-full bg-surface px-2 py-0.5 text-[12px] whitespace-nowrap text-muted-foreground">
                {part}
              </span>
            ))}
          </span>
        )}
        <ChevronDown
          aria-hidden="true"
          className={cn("size-4 shrink-0 text-muted-foreground transition-transform duration-300", open && "rotate-180")}
        />
      </button>

      {/* A grid whose single row goes 0fr → 1fr animates a height nobody has to measure. */}
      <div
        className={cn(
          "grid transition-[grid-template-rows] duration-400 ease-[cubic-bezier(.2,.8,.2,1)]",
          open ? "grid-rows-[1fr]" : "grid-rows-[0fr]",
        )}
      >
        <div className={cn("min-h-0 overflow-hidden", !open && "invisible")}>
          <ol className="mt-4 mb-1 ml-2.5">
            {events.map((event, index) => {
              const step = sentence(event);
              // The last row pulses only while the run is still going.
              const active = live && index === events.length - 1;
              const last = index === events.length - 1;
              return (
                <li
                  key={event.seq}
                  className={cn("relative animate-fade-up pl-7", last ? "pb-1" : "pb-3.5")}
                  style={{ animationDelay: `${Math.min(index, 6) * 60}ms` }}
                >
                  <span
                    aria-hidden="true"
                    className={cn(
                      "absolute top-[5px] left-0 size-[11px] rounded-full border-2 transition-colors",
                      active ? "animate-ring border-brand bg-brand-soft" : "border-brand bg-brand",
                    )}
                  />
                  {!last && (
                    <span aria-hidden="true" className="absolute top-5 bottom-0 left-[4.75px] w-[1.5px] bg-border" />
                  )}
                  <span className={cn("block text-[14px] font-medium text-text", TONE_CLASS[event.type])}>
                    {step.lead}
                    {event.type === "model_called" && (
                      <span className="ml-1.5 rounded-full bg-brand-soft px-1.5 py-px align-middle text-[11px] font-semibold text-brand">
                        Meta
                      </span>
                    )}
                  </span>
                  {step.rest && (
                    <span className="block text-[13.5px] leading-relaxed text-muted-foreground">{step.rest}</span>
                  )}
                </li>
              );
            })}
          </ol>
        </div>
      </div>
    </div>
  );
}