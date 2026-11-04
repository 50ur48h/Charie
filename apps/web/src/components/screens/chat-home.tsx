"use client";

/** Where a chat begins: a greeting, a composer, and nothing to configure first (WP13.1b). */

import { Database, Lightbulb, TrendingUp, Trophy, TriangleAlert } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { Composer } from "@/components/answer/composer";
import { BrandMark } from "@/components/shell/brand";
import { TopBar } from "@/components/shell/top-bar";
import { Pending } from "@/components/ui/pending";
import { ApiError, createApi, type ActiveDataSource, type DataSource } from "@/lib/api-client";
import { useSession } from "@/lib/auth/session";
import { useOrgRole } from "@/lib/use-org-role";

/** Starting points. They fill the composer rather than send. */
const STARTERS = [
  { icon: TrendingUp, text: "How are sales doing this month compared with last month?" },
  { icon: Trophy, text: "What are our five best-selling products by revenue?" },
  { icon: TriangleAlert, text: "Which locations are performing worst, and why?" },
  { icon: Lightbulb, text: "What changed the most over the last quarter?" },
];

export function ChatHome({ orgId }: { orgId: string }) {
  const session = useSession();
  const router = useRouter();
  const api = useMemo(() => createApi(session.getToken), [session.getToken]);
  const { role } = useOrgRole(orgId);

  const [question, setQuestion] = useState("");
  const [active, setActive] = useState<ActiveDataSource | null>(null);
  // Read alongside the choice so this screen can tell the truth about whether asking will work.
  const [sources, setSources] = useState<DataSource[] | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const box = useRef<HTMLTextAreaElement | null>(null);

  /** One key per draft, so a retry after a timeout replays it (D-019). */
  const idempotencyKey = useRef<string>(crypto.randomUUID());

  /** A thread created before its first question failed to post; reused on retry. */
  const pending = useRef<string | null>(null);

  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const [chosen, registered] = await Promise.all([
          api.activeDataSource(orgId),
          api.dataSources(orgId),
        ]);
        if (!alive) return;
        setActive(chosen);
        setSources(registered);
      } catch (cause) {
        if (alive) {
          setError(cause instanceof ApiError ? cause.message : "This page could not be loaded.");
        }
      }
    })();
    return () => {
      alive = false;
    };
  }, [api, orgId]);

  const send = useCallback(async () => {
    const content = question.trim();
    if (content.length === 0) return;

    setSending(true);
    setError(null);
    try {
      const conversationId = pending.current ?? (await api.createConversation(orgId, {})).id;
      pending.current = conversationId;
      await api.ask(orgId, conversationId, content, idempotencyKey.current);
      // Only past this point is the question definitely on its way.
      idempotencyKey.current = crypto.randomUUID();
      pending.current = null;
      router.push(`/orgs/${orgId}/conversations/${conversationId}`);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "That question could not be sent.");
      setSending(false);
    }
  }, [api, orgId, question, router]);

  /** The database a question asked right now would actually reach, or null. */
  const answersFrom =
    active?.data_source_name ?? (sources?.length === 1 ? (sources[0]?.name ?? null) : null);

  // `null` while loading, so nothing claims a database is missing early.
  const loaded = active !== null && sources !== null;
  const ready = answersFrom !== null;
  const several = (sources?.length ?? 0) > 1;
  const isAdmin = role === "admin";

  // Focus once there is something to ask about; a disabled field cannot take it.
  useEffect(() => {
    if (ready) box.current?.focus();
  }, [ready]);

  const pick = (text: string) => {
    setQuestion(text);
    box.current?.focus();
  };

  return (
    <div className="flex min-h-full flex-col">
      <TopBar sticky={false} />
      <div className="mx-auto flex w-full max-w-[760px] flex-1 flex-col justify-center px-4 pb-16 sm:px-7">
        <div className="mb-7 flex animate-fade-up flex-col items-center text-center">
          <BrandMark className="mb-5 size-11 text-brand" />
          <h1 className="font-serif text-[30px] leading-tight font-semibold tracking-[-0.015em] text-text sm:text-[34px]">
            What would you like to know?
          </h1>
          {loaded &&
            (ready ? (
              <p className="mt-3 inline-flex items-center gap-2 rounded-full bg-surface-2 px-3 py-1 text-[13px] text-text-2">
                <Database aria-hidden="true" className="size-3.5 text-brand" />
                <span>
                  Answered from <strong className="font-semibold text-text">{answersFrom}</strong>
                </span>
              </p>
            ) : (
              <p className="mt-3 max-w-[56ch] text-[14px] leading-relaxed text-warn-ink">
                {several
                  ? isAdmin
                    ? "This organization has more than one database and none is chosen, so a question has nowhere to go. Choose one in Settings → Data sources."
                    : "This organization has more than one database and none is chosen, so a question has nowhere to go. An Admin can choose one."
                  : isAdmin
                    ? "No database is registered yet, so there is nothing to ask about. Add one in Settings → Data sources."
                    : "No database is registered yet, so there is nothing to ask about. An Admin can add one."}
              </p>
            ))}
        </div>

        {/* Your question, the moment you send it — faint until it is real (D-049). */}
        {sending && (
          <div className="mb-5 grid animate-fade-up gap-3">
            <p className="ml-auto max-w-[78%] rounded-[20px] bg-bubble px-[18px] py-2.5 text-[15.5px] whitespace-pre-wrap opacity-60">
              {question.trim()}
            </p>
            <Pending>Sending your question…</Pending>
          </div>
        )}

        <div className="animate-fade-up [animation-delay:80ms]">
          <Composer
            label="Your question"
            value={question}
            onChange={setQuestion}
            onSend={() => void send()}
            disabled={!ready}
            sending={sending}
            inputRef={box}
            placeholder="Ask Charie anything about your business…"
            onAttach={() =>
              toast("Documents live in Knowledge, where Charie reads them before it queries.", {
                action: { label: "Open Knowledge", onClick: () => router.push(`/orgs/${orgId}/documents`) },
              })
            }
          />
        </div>

        {error && (
          <p role="alert" className="mt-3 text-center text-[13.5px] text-bad-ink">
            {error}
          </p>
        )}

        {ready && !sending && (
          <div className="mt-8 animate-fade-up [animation-delay:160ms]">
            <p className="mb-2.5 text-center text-[12px] font-semibold text-muted-foreground">
              Try asking
            </p>
            <div className="grid gap-2 sm:grid-cols-2">
              {STARTERS.map(({ icon: Icon, text }) => (
                <button
                  key={text}
                  type="button"
                  onClick={() => pick(text)}
                  className="flex items-start gap-2.5 rounded-xl border border-border bg-surface px-3.5 py-3 text-left text-[13.5px] leading-snug text-text-2 shadow-[0_1px_2px_rgba(var(--shadow-rgb),.04)] transition-[border-color,transform,box-shadow] hover:-translate-y-px hover:border-brand hover:shadow-[0_6px_16px_rgba(var(--shadow-rgb),.08)]"
                >
                  <Icon aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-brand" />
                  <span>{text}</span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
