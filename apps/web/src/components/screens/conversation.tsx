"use client";

/** One thread of questions, and the answers with their evidence (plan WP7.3). */

import { CircleX, Share2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { AnswerActions, FollowUps, STATUS_WORDS, outcome } from "@/components/answer/answer-actions";
import { AnswerChart } from "@/components/answer/answer-chart";
import { AnswerMarkdown } from "@/components/answer/answer-markdown";
import { Callout } from "@/components/answer/callout";
import { Composer } from "@/components/answer/composer";
import { HowIWorked } from "@/components/answer/how-worked";
import { Trace } from "@/components/screens/trace";
import { BrandMark } from "@/components/shell/brand";
import { TopBar } from "@/components/shell/top-bar";
import { Hint } from "@/components/ui/tooltip";
import {
  ApiError,
  createApi,
  type Conversation,
  type ConversationMessage,
  type Run,
} from "@/lib/api-client";
import { useSession } from "@/lib/auth/session";
import { cn } from "@/lib/utils";

/** How often a live run is asked how it is getting on. */
const POLL_MS = 1500;

/** Statuses a run never leaves, so polling stops (`runs/service.py`). */
const TERMINAL = new Set(["completed", "interrupted", "failed", "budget_exhausted"]);

/** How far through its allowance a run is (B-177): counters, never a prediction. */
export function progressLine(run: Run): string | null {
  const used = run.progress?.used;
  const limits = run.progress?.limits;
  if (!used || !limits) return null;

  const parts: string[] = [];
  if (typeof used.iterations === "number" && typeof limits.iterations === "number") {
    parts.push(`step ${used.iterations} of ${limits.iterations}`);
  }
  if (typeof used.wall_seconds === "number" && typeof limits.wall_seconds === "number") {
    parts.push(`${clock(used.wall_seconds)} of ${clock(limits.wall_seconds)}`);
  }
  return parts.length > 0 ? parts.join(" · ") : null;
}

/** Seconds as m:ss. Minutes, because a run is minutes and 330 is not readable. */
function clock(seconds: number): string {
  const whole = Math.max(0, Math.round(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

/** Whether this run is close enough to a ceiling to say so. */
export function nearlyOut(run: Run): boolean {
  const used = run.progress?.used;
  const limits = run.progress?.limits;
  if (!used || !limits) return false;
  const share = (a?: number, b?: number) =>
    typeof a === "number" && typeof b === "number" && b > 0 ? a / b : 0;
  return (
    share(used.iterations, limits.iterations) >= 0.75 ||
    share(used.wall_seconds, limits.wall_seconds) >= 0.75
  );
}

/** Whether a cell holds a number rather than words (B-179). */
export function isNumeric(children: React.ReactNode): boolean {
  const text = flatten(children).trim();
  if (text.length === 0) return false;
  return /^[-+(]?\s*(RM|MYR|\$|€|£)?\s*[\d,]+(\.\d+)?\s*%?\s*\)?$/i.test(text);
}

function flatten(node: React.ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(flatten).join("");
  if (node && typeof node === "object" && "props" in node) {
    return flatten((node as { props: { children?: React.ReactNode } }).props.children);
  }
  return "";
}

/** What the answer does not establish — a ceiling that stopped the search, a reviewer's warning. */
function Limitations({ notes }: { notes: string[] }) {
  if (notes.length === 0) return null;
  return (
    <Callout
      title={notes.length === 1 ? "One thing to know" : `${notes.length} things to know`}
      label="What this answer does not establish"
    >
      {notes.length === 1 ? (
        <p>{notes[0]}</p>
      ) : (
        <ul className="list-disc space-y-1 pl-5 marker:text-warn">
          {notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}
    </Callout>
  );
}

/** A few natural next questions, offered after the latest answer. */
function nextQuestions(run: Run, words: string | null): string[] {
  const state = outcome(run);
  if (run.status !== "completed" || state === "refused") return [];
  // A table in the answer is drawn as a chart already, so offer to dig instead.
  const pictured = Boolean(run.chart?.spec) || /\n\s*\|.*\|\s*\n\s*\|?\s*:?-{3,}/.test(words ?? "");
  return [
    pictured ? "Which of these stand out, and why?" : "Show this as a chart",
    "What is driving this?",
    "How does this compare with the period before?",
  ];
}

function UserTurn({ text, faint = false }: { text: string; faint?: boolean }) {
  return (
    <li className="flex animate-fade-up justify-end">
      <p
        className={cn(
          "max-w-[78%] rounded-[20px] bg-bubble px-[18px] py-2.5 text-[15.5px] leading-normal whitespace-pre-wrap text-text",
          faint && "opacity-60",
        )}
      >
        {text}
      </p>
    </li>
  );
}

function AgentTurn({ children }: { children: React.ReactNode }) {
  return (
    <li className="flex animate-fade-up items-start gap-3.5">
      <BrandMark className="mt-0.5 size-7 text-brand" />
      <div className="min-w-0 flex-1">{children}</div>
    </li>
  );
}

/** The reply, and what stands behind it. */
function AnswerCard({
  orgId,
  run,
  answer,
  latest,
  onCorrect,
  onPick,
}: {
  orgId: string;
  run: Run;
  /** The words this turn said, when the card is rendering a message (B-044). */
  answer?: string | undefined;
  latest: boolean;
  onCorrect: (note: string) => void;
  onPick: (question: string) => void;
}) {
  const words = answer ?? run.answer;
  const failed = run.status === "failed";
  return (
    <>
      <Trace
        orgId={orgId}
        runId={run.id}
        live={false}
        startedAt={run.started_at}
        finishedAt={run.finished_at}
      />
      <div className="flex flex-col gap-4" data-testid="answer">
        {failed ? (
          <Callout tone="bad" icon={<CircleX />} title="This question could not be completed">
            <p>
              {run.failure_reason ??
                "Something went wrong on our side while answering this. Nothing was wrong with the question."}
            </p>
          </Callout>
        ) : (
          <>
            {words && <AnswerMarkdown words={words} />}
            <AnswerChart chart={run.chart} />
            <Limitations notes={run.limitations ?? []} />
            <HowIWorked orgId={orgId} run={run} answer={words} />
          </>
        )}
      </div>
      <AnswerActions run={run} words={words} onCorrect={failed ? undefined : onCorrect} />
      {latest && <FollowUps suggestions={nextQuestions(run, words)} onPick={onPick} />}
    </>
  );
}

/** What a live run is doing, from its own trace (D-047) — not a bare spinner. */
function RunProgress({ orgId, run }: { orgId: string; run: Run }) {
  const line = progressLine(run);
  const close = nearlyOut(run);
  return (
    <>
      <Trace
        orgId={orgId}
        runId={run.id}
        live
        defaultOpen
        startedAt={run.started_at}
        finishedAt={run.finished_at}
      />
      <div className="font-sans">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] text-muted-foreground">
          <span className="inline-flex items-center gap-1.5 font-semibold text-brand-ink">
            <span aria-hidden="true" className="size-1.5 animate-pulse rounded-full bg-brand" />
            <span>{STATUS_WORDS[run.status] ?? run.status}</span>
          </span>
          {line && (
            <span className={close ? "text-warn-ink" : undefined}>
              · {line}
              {close && " — close to its limit, so the answer may be partial"}
            </span>
          )}
        </div>
        <p className="mt-1 text-[13px] text-muted-foreground">
          The answer arrives here on its own — you can leave the page and come back to it.
        </p>
      </div>
    </>
  );
}

function SourcePill({ name }: { name: string | null }) {
  if (!name) {
    return (
      <span className="hidden items-center rounded-full bg-warn-soft px-3 py-[5px] text-[12.5px] font-medium text-warn-ink sm:inline-flex">
        no database chosen
      </span>
    );
  }
  return (
    <Hint label="The database this chat answers from">
      <span className="hidden max-w-[240px] items-center gap-2 rounded-full bg-surface-2 px-3 py-[5px] text-[12.5px] text-text-2 sm:inline-flex">
        <span aria-hidden="true" className="size-[7px] shrink-0 rounded-full bg-brand shadow-[0_0_0_3px_var(--accent-soft)]" />
        <span className="truncate">{name}</span>
      </span>
    </Hint>
  );
}

export function ConversationThread({
  orgId,
  conversationId,
}: {
  orgId: string;
  conversationId: string;
}) {
  const session = useSession();
  const router = useRouter();
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [run, setRun] = useState<Run | null>(null);
  /** Every answered run in the thread, by id (B-106). */
  const [runs, setRuns] = useState<Map<string, Run>>(new Map());
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const composer = useRef<HTMLTextAreaElement | null>(null);

  // Held across retries of one draft.
  const idempotencyKey = useRef<string | null>(null);

  // The run whose thread has already been re-read after it finished.
  const reconciled = useRef<string | null>(null);

  const api = useMemo(() => createApi(session.getToken), [session.getToken]);

  const loadThread = useCallback(async () => {
    try {
      const [details, thread, answered] = await Promise.all([
        api.conversation(orgId, conversationId),
        api.messages(orgId, conversationId),
        // One request for every run in the thread (B-106).
        api.conversationRuns(orgId, conversationId).catch(() => null),
      ]);
      setConversation(details);
      setMessages(thread);
      if (answered !== null) setRuns(new Map(answered.map((found) => [found.id, found])));
      return details;
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "This conversation could not be loaded.");
      return null;
    }
  }, [api, orgId, conversationId]);

  useEffect(() => {
    void (async () => {
      const details = await loadThread();
      // Pick up a run that was still going when the page was last closed.
      if (details?.last_run_id) {
        try {
          const existing = await api.run(orgId, details.last_run_id);
          if (TERMINAL.has(existing.status)) reconciled.current = existing.id;
          setRun(existing);
        } catch {
          // The messages are the conversation, and they are already shown.
        }
      }
    })();
  }, [loadThread, api, orgId]);

  const runId = run?.id ?? null;
  const runStatus = run?.status ?? null;
  const live = runId !== null && runStatus !== null && !TERMINAL.has(runStatus);

  /** Watch a live run until it stops. */
  useEffect(() => {
    if (!live || runId === null) return;

    let cancelled = false;
    const tick = async () => {
      try {
        const latest = await api.run(orgId, runId);
        if (cancelled) return;
        setRun(latest);
      } catch {
        // A dropped poll is not worth an error banner: the next tick asks again.
      }
    };

    const timer = setInterval(() => void tick(), POLL_MS);
    void tick();
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [api, orgId, runId, live]);

  /** When a run finishes, re-read the thread once — the reply is a message. */
  useEffect(() => {
    if (runId === null || runStatus === null || !TERMINAL.has(runStatus)) return;
    if (reconciled.current === runId) return;
    reconciled.current = runId;

    void loadThread();
  }, [runId, runStatus, loadThread]);

  const ask = useCallback(
    async (question: string, key: string) => {
      setSending(true);
      setPendingQuestion(question);
      setError(null);
      try {
        const accepted = await api.ask(orgId, conversationId, question, key);
        await loadThread();
        // The thread now holds the question itself, so the faint copy goes.
        setPendingQuestion(null);
        setRun(await api.run(orgId, accepted.run_id));
        return true;
      } catch (cause) {
        setError(cause instanceof ApiError ? cause.message : "That question could not be sent.");
        return false;
      } finally {
        setSending(false);
        setPendingQuestion(null);
      }
    },
    [api, orgId, conversationId, loadThread],
  );

  const send = useCallback(async () => {
    const question = draft.trim();
    if (!question || sending) return;
    idempotencyKey.current ??= crypto.randomUUID();
    const sent = await ask(question, idempotencyKey.current);
    // On failure the key is deliberately kept.
    if (sent) {
      setDraft("");
      idempotencyKey.current = null;
    }
  }, [draft, sending, ask]);

  /** "This is wrong": the correction goes back as the next question. */
  const correct = useCallback(
    (note: string) => {
      if (sending || live) {
        toast("A question is still running. Send the correction once it has answered.");
        return;
      }
      void ask(`That answer looks wrong: ${note}. Please check it again.`, crypto.randomUUID());
    },
    [ask, sending, live],
  );

  const pick = useCallback((question: string) => {
    setDraft(question);
    composer.current?.focus();
  }, []);

  const answered = run !== null && TERMINAL.has(run.status);

  /** The run to render for an assistant message; the live one wins where they overlap. */
  const runFor = (messageRunId: string | null): Run | null => {
    if (messageRunId === null) return null;
    const found = run !== null && run.id === messageRunId ? run : (runs.get(messageRunId) ?? null);
    return found !== null && TERMINAL.has(found.status) ? found : null;
  };

  /** Whether the live run already has its reply in the thread (B-044). */
  const liveRunIsInThread =
    run !== null && messages.some((message) => message.run_id === run.id && message.role === "assistant");

  const lastAssistant = [...messages].reverse().find((message) => message.role === "assistant");

  // Follow the conversation to its end: on arrival.
  const settledOnce = useRef(false);
  useEffect(() => {
    const scroller = document.getElementById("main");
    if (!scroller || messages.length === 0) return;
    const near = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 240;
    if (!settledOnce.current || near) {
      settledOnce.current = true;
      requestAnimationFrame(() => scroller.scrollTo({ top: scroller.scrollHeight, behavior: "smooth" }));
    }
  }, [messages.length, runStatus, pendingQuestion]);

  const share = useCallback(() => {
    void navigator.clipboard
      ?.writeText(window.location.href)
      .then(() => toast("Link copied. Only you can open your own chats."))
      .catch(() => toast("The link could not be copied."));
  }, []);

  return (
    <div className="flex min-h-full flex-col">
      <TopBar title={conversation?.title ?? ""}>
        {conversation && <SourcePill name={conversation.data_source_name} />}
        <Hint label="Copy a link to this chat">
          <button
            type="button"
            aria-label="Copy a link to this chat"
            onClick={share}
            className="grid size-8 place-items-center rounded-sm text-muted-foreground transition-colors hover:bg-surface-2 hover:text-text"
          >
            <Share2 aria-hidden="true" className="size-[17px]" />
          </button>
        </Hint>
      </TopBar>

      <div className="mx-auto w-full max-w-[800px] flex-1 px-4 pt-4 pb-8 sm:px-7">
        {conversation && !conversation.data_source_id && (
          <div className="mb-6">
            <Callout tone="note" title="This chat is not tied to a database">
              <p className="text-[15px]">
                If this organization has exactly one, questions here are answered against it; if it
                has several, they will be refused until you start a chat that names one.
              </p>
            </Callout>
          </div>
        )}

        <ol className="grid gap-9">
          {messages.map((message) => {
            if (message.role === "user") return <UserTurn key={message.id} text={message.content} />;
            const answering = runFor(message.run_id);
            return (
              <AgentTurn key={message.id}>
                {answering ? (
                  <AnswerCard
                    orgId={orgId}
                    run={answering}
                    answer={message.content}
                    latest={message.id === lastAssistant?.id && !live}
                    onCorrect={correct}
                    onPick={pick}
                  />
                ) : (
                  // The words are still the answer when the run could not be fetched.
                  <AnswerMarkdown words={message.content} />
                )}
              </AgentTurn>
            );
          })}

          {sending && pendingQuestion && <UserTurn text={pendingQuestion} faint />}

          {live && run && (
            <AgentTurn>
              <RunProgress orgId={orgId} run={run} />
            </AgentTurn>
          )}

          {/* The live run's card, until its message joins the thread (B-044). */}
          {answered && run && !liveRunIsInThread && (
            <AgentTurn>
              <AnswerCard orgId={orgId} run={run} latest onCorrect={correct} onPick={pick} />
            </AgentTurn>
          )}
        </ol>
      </div>

      <div className="sticky bottom-0 z-10 bg-gradient-to-t from-background from-70% to-transparent px-4 pt-6 pb-3 sm:px-7">
        <div className="mx-auto max-w-[800px]">
          {live && !sending && (
            <p className="mb-2 text-center font-sans text-[12.5px] text-muted-foreground">
              A question is already running; you can write the next one meanwhile.
            </p>
          )}
          {error && (
            <p role="alert" className="mb-2 text-center font-sans text-[13px] text-bad-ink">
              {error}
            </p>
          )}
          <Composer
            label="Ask a question"
            value={draft}
            onChange={setDraft}
            onSend={() => void send()}
            sending={sending}
            inputRef={composer}
            onAttach={() =>
              toast("Documents live in Knowledge, where Charie reads them before it queries.", {
                action: { label: "Open Knowledge", onClick: () => router.push(`/orgs/${orgId}/documents`) },
              })
            }
          />
        </div>
      </div>
    </div>
  );
}
