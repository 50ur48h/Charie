// The new-chat page (Calm home.html): greeting, sample questions, the
// question box, the questions notice and recent chats.
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { ArrowUpDown, Inbox, ScanSearch, TrendingUp, Trophy } from "lucide-react";
import { ApiError } from "@charie/shared";
import { StillLearning } from "./StillLearning";
import {
  Button,
  IconBox,
  LogoMark,
  QuestionComposer,
  toast,
  useChats,
  useCreateChat,
  useSendMessage,
  useStatus,
} from "@charie/shared";

const IDEA_CARDS = [
  { kind: "How we're doing", text: "How are we doing this month?", icon: TrendingUp },
  { kind: "Biggest changes", text: "What changed the most last month?", icon: ArrowUpDown },
  { kind: "Find out why", text: "Why did sales change last month?", icon: ScanSearch },
  { kind: "Best and worst", text: "Which are our best performers?", icon: Trophy },
];

const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

function relativeDay(isoDate: string): string {
  const then = new Date(isoDate);
  const now = new Date();
  const days =
    new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime() -
    new Date(then.getFullYear(), then.getMonth(), then.getDate()).getTime();
  const count = Math.round(days / 86_400_000);
  if (count <= 0) return "Today";
  if (count === 1) return "Yesterday";
  return `${then.getDate()} ${MONTHS[then.getMonth()]}`;
}

export function NewChatPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  // "Ask Charie about this" links here with ?draft= filled in.
  const [draft, setDraft] = useState(() => searchParams.get("draft") ?? "");
  const [sending, setSending] = useState(false);
  const sendingRef = useRef(false);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const focusedDraft = useRef(false);
  // "Ask Charie about this" links here with ?draft= filled in: focus the box
  // with the cursor at the end. Nothing is ever sent on its own.
  useEffect(() => {
    if (!focusedDraft.current && draft !== "" && composerRef.current) {
      focusedDraft.current = true;
      composerRef.current.focus();
      composerRef.current.setSelectionRange(draft.length, draft.length);
    }
  }, [draft]);
  const createChat = useCreateChat();
  const sendMessage = useSendMessage();
  const statusQuery = useStatus();
  const chatsQuery = useChats();

  const waiting = statusQuery.data?.questions_waiting ?? 0;
  const recent = (chatsQuery.data ?? []).slice(0, 3);
  // Before the first published version, the ideas make way for the
  // still-learning card and the question box stays disabled (P12.1).
  const stillLearning =
    statusQuery.data !== undefined && (statusQuery.data?.knowledge?.version ?? null) === null;

  async function submit(): Promise<void> {
    const text = draft.trim();
    // The ref guard makes a double submit a single chat even before React
    // re-renders with sending=true.
    if (text === "" || sendingRef.current) return;
    sendingRef.current = true;
    setSending(true);
    try {
      const chat = await createChat.mutateAsync();
      await sendMessage.mutateAsync({ chatId: chat.id, text });
      setDraft("");
      await navigate(`/chat/${chat.id}`);
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Something went wrong on our side. Please try again.");
    } finally {
      sendingRef.current = false;
      setSending(false);
    }
  }

  return (
    <div className="mx-auto w-full max-w-[820px] px-7 pt-[8vh] pb-12">
      <div className="mb-[26px] text-center">
        <div className="mx-auto mb-[18px] w-[52px] text-accent">
          <LogoMark size={52} />
        </div>
        <h1 className="m-0 font-serif text-[38px] font-semibold tracking-[-0.01em]">
          {greeting()}
        </h1>
        <p className="mt-2 text-[16px] text-muted">
          Ask anything about your business. Charie checks every number before it shows it.
        </p>
      </div>

      <div className="print:hidden">
      <QuestionComposer
        large
        value={draft}
        onChange={setDraft}
        onSubmit={() => void submit()}
        sending={sending}
        dataThrough={statusQuery.data?.data?.data_through ?? null}
        textareaRef={composerRef}
        disabled={stillLearning}
        disabledPlaceholder="You can ask once Charie has finished learning."
      />
      </div>

      {stillLearning ? (
        <div className="mt-[18px]">
          <StillLearning
            learning={statusQuery.data?.learning ?? null}
            learnerUrl={statusQuery.data?.learner_url ?? null}
          />
        </div>
      ) : (
      <div className="mt-[18px] grid grid-cols-1 gap-3 sm:grid-cols-2">
        {IDEA_CARDS.map(({ kind, text, icon }) => (
          <button
            key={text}
            type="button"
            onClick={() => {
              setDraft(text);
              composerRef.current?.focus();
            }}
            className="flex items-start gap-3 rounded-[16px] border border-border bg-surface/70 p-[14px_16px] text-left transition-[border-color,transform,box-shadow,background] duration-200 hover:-translate-y-0.5 hover:border-focus hover:bg-surface hover:shadow-[0_10px_24px_rgba(var(--shadow-rgb),.08)]"
          >
            <IconBox icon={icon} />
            <span>
              <span className="text-[11.5px] font-semibold tracking-[0.05em] text-accent-ink uppercase">
                {kind}
              </span>
              <span className="mt-0.5 block font-serif text-[16.5px] leading-[1.4]">{text}</span>
            </span>
          </button>
        ))}
      </div>
      )}

      {waiting > 0 && (
        <div className="mt-[26px] flex items-center gap-[14px] rounded-[16px] bg-accent-soft p-[14px_16px] text-accent-ink">
          <IconBox icon={Inbox} />
          <div>
            <b className="text-text">
              {waiting === 1 ? "1 question needs your answer." : `${waiting} questions need your answer.`}{" "}
            </b>
            Until then, Charie uses sensible defaults and tells you when it does.
          </div>
          <Button asChild size="sm" className="ml-auto flex-none">
            <Link to="/questions">Answer now</Link>
          </Button>
        </div>
      )}

      {recent.length > 0 && (
        <>
          <div className="mt-8 mb-3 text-[13px] font-semibold tracking-[0.04em] text-muted uppercase">
            Pick up where you left off
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {recent.map((chat) => (
              <Link
                key={chat.id}
                to={`/chat/${chat.id}`}
                className="rounded-[14px] border border-border bg-surface p-[14px_16px] transition-[border-color,box-shadow] duration-200 hover:border-focus hover:shadow-[0_6px_18px_rgba(var(--shadow-rgb),.07)]"
              >
                <div className="text-[14px] font-semibold">{chat.title}</div>
                <div className="mt-1 text-[12.5px] text-muted">{relativeDay(chat.updated_at)}</div>
              </Link>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
