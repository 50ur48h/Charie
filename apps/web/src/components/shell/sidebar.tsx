"use client";

/**
 * The sidebar: the mark, a new chat, the two places a person returns to, your
 * threads by day, and the way into Settings.
 *
 * **Every role sees this, and it holds no admin controls.** Architecture 6.2
 * grants "ask questions / view own conversations & traces" to every role, and
 * the list shows only your own. Data sources and Members live behind Settings,
 * where they gate themselves.
 *
 * **"Archive" says archive** (D-039). Nothing is destroyed: the runs, their
 * events, their findings and their query executions stay where they are. So the
 * control names the true action and the confirmation says it can be undone.
 *
 * **Collapsed or expanded survives a reload**, in `localStorage`, per browser.
 */

import {
  Archive,
  BookOpen,
  Inbox,
  PanelLeftClose,
  PanelLeftOpen,
  Pencil,
  Settings,
  SquarePen,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { SkeletonList } from "@/components/ui/skeleton";
import { Hint } from "@/components/ui/tooltip";
import { ApiError, createApi, type Conversation } from "@/lib/api-client";
import { useSession } from "@/lib/auth/session";
import { personLabel, type Named } from "@/lib/identity";
import { cn } from "@/lib/utils";

import { BrandMark, Wordmark } from "./brand";
import { useSidebarCollapsed } from "./collapsed";

/**
 * Up to two letters for the avatar, from whatever the identity provider sent.
 * Falls back to the subject, and to a dot when even that is missing.
 */
export function initials(person: Named | null, subject: string | null): string {
  const source = person?.name?.trim() || person?.email?.split("@")[0] || subject || "";
  const parts = source.split(/[\s._-]+/).filter(Boolean);
  const letters = parts.slice(0, 2).map((part) => part[0] ?? "");
  return letters.join("").toUpperCase() || "·";
}

/** A thread with no title yet is shown by what it is, not by a blank. */
function threadLabel(conversation: Conversation): string {
  const title = conversation.title?.trim();
  return title && title.length > 0 ? title : "New chat";
}

const DAY = 86_400_000;

/** Threads by when they were started: Today, Yesterday, the last week, and so on. */
export function groupByDay(
  threads: Conversation[],
  now: Date = new Date(),
): { label: string; items: Conversation[] }[] {
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const buckets: { label: string; from: number; items: Conversation[] }[] = [
    { label: "Today", from: today, items: [] },
    { label: "Yesterday", from: today - DAY, items: [] },
    { label: "Previous 7 days", from: today - 7 * DAY, items: [] },
    { label: "Previous 30 days", from: today - 30 * DAY, items: [] },
    { label: "Older", from: Number.NEGATIVE_INFINITY, items: [] },
  ];
  for (const thread of threads) {
    const at = new Date(thread.created_at).getTime();
    const when = Number.isNaN(at) ? Number.NEGATIVE_INFINITY : at;
    (buckets.find((bucket) => when >= bucket.from) ?? buckets[buckets.length - 1]!).items.push(thread);
  }
  return buckets.filter((bucket) => bucket.items.length > 0);
}

function NavItem({
  href,
  icon,
  label,
  badge,
  active,
  onNavigate,
}: {
  href: string;
  icon: ReactNode;
  label: string;
  badge?: number | undefined;
  active: boolean;
  onNavigate?: (() => void) | undefined;
}) {
  return (
    <Link
      href={href}
      onClick={() => onNavigate?.()}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex items-center gap-2.5 rounded-[10px] px-3 py-2 text-[14px] text-text-2 transition-colors hover:bg-[rgba(var(--shadow-rgb),.05)] [&_svg]:size-[17px] [&_svg]:text-muted-foreground",
        active && "bg-surface font-medium text-text shadow-[0_1px_2px_rgba(var(--shadow-rgb),.07)]",
      )}
    >
      {icon}
      <span className="truncate">{label}</span>
      {badge ? (
        <span className="ml-auto grid h-5 min-w-5 place-items-center rounded-full bg-brand px-1.5 text-[11.5px] font-semibold text-on-brand">
          {badge}
        </span>
      ) : null}
    </Link>
  );
}

function RailLink({
  href,
  label,
  children,
  active = false,
  dot = false,
}: {
  href: string;
  label: string;
  children: ReactNode;
  active?: boolean;
  dot?: boolean;
}) {
  return (
    <Hint label={label} side="right">
      <Link
        href={href}
        aria-label={label}
        className={cn(
          "relative grid size-9 place-items-center rounded-[10px] text-muted-foreground transition-colors hover:bg-[rgba(var(--shadow-rgb),.06)] hover:text-text [&_svg]:size-[18px]",
          active && "bg-surface text-text shadow-[0_1px_2px_rgba(var(--shadow-rgb),.07)]",
        )}
      >
        {children}
        {dot && <span className="absolute top-1.5 right-1.5 size-2 rounded-full bg-brand ring-2 ring-sidebar" />}
      </Link>
    </Hint>
  );
}

export function Sidebar({
  orgId,
  orgName,
  person,
  pendingQuestions = 0,
  questionsHref = null,
  inSheet = false,
  onNavigate,
}: {
  orgId: string;
  orgName: string | null;
  person: Named | null;
  /** Imported definitions waiting for an Admin (B-059). */
  pendingQuestions?: number;
  /** Where those questions are answered, or null when there is nowhere yet. */
  questionsHref?: string | null;
  /** Rendered inside the small-screen drawer: always expanded, no collapse. */
  inSheet?: boolean;
  /** Called after a link is followed, so the drawer can close. */
  onNavigate?: (() => void) | undefined;
}) {
  const session = useSession();
  const pathname = usePathname();
  const api = useMemo(() => createApi(session.getToken), [session.getToken]);

  // `null` is "not loaded yet", which is a different claim from "you have none".
  const [conversations, setConversations] = useState<Conversation[] | null>(null);
  const [storedCollapsed, toggleCollapsed] = useSidebarCollapsed();
  const collapsed = storedCollapsed && !inSheet;
  const [renaming, setRenaming] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const home = `/orgs/${orgId}/conversations`;
  const knowledgeHref = `/orgs/${orgId}/documents`;
  const settingsHref = `/orgs/${orgId}/settings`;

  const load = useCallback(async () => {
    const threads = await api.conversations(orgId, { archived: false });
    setConversations(threads);
  }, [api, orgId]);

  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const threads = await api.conversations(orgId, { archived: false });
        if (alive) setConversations(threads);
      } catch (cause) {
        if (alive) {
          setError(cause instanceof ApiError ? cause.message : "Your chats could not be loaded.");
        }
      }
    })();
    return () => {
      alive = false;
    };
    // `pathname` is a dependency on purpose: starting a new chat navigates, and
    // the sidebar has to show the thread that was just created without a reload.
  }, [api, orgId, pathname]);

  const rename = useCallback(
    async (conversationId: string) => {
      const title = draft.trim();
      if (title.length === 0) {
        setRenaming(null);
        return;
      }
      setBusy(conversationId);
      setError(null);
      try {
        await api.renameConversation(orgId, conversationId, title);
        setRenaming(null);
        await load();
      } catch (cause) {
        setError(cause instanceof ApiError ? cause.message : "That chat could not be renamed.");
      } finally {
        setBusy(null);
      }
    },
    [api, orgId, draft, load],
  );

  const archive = useCallback(
    async (conversationId: string) => {
      setBusy(conversationId);
      setError(null);
      try {
        await api.archiveConversation(orgId, conversationId, true);
        setConfirming(null);
        await load();
      } catch (cause) {
        setError(cause instanceof ApiError ? cause.message : "That chat could not be archived.");
      } finally {
        setBusy(null);
      }
    },
    [api, orgId, load],
  );

  const groups = useMemo(() => (conversations ? groupByDay(conversations) : []), [conversations]);
  const who = initials(person, session.who);

  if (collapsed) {
    return (
      <nav
        className="flex h-full w-[60px] flex-col items-center gap-1 bg-sidebar py-3.5"
        aria-label="Chats"
      >
        <Link href={home} aria-label="Charie home" className="mb-2 text-brand">
          <BrandMark className="size-7" />
        </Link>
        <Hint label="Expand the sidebar" side="right">
          <button
            type="button"
            onClick={toggleCollapsed}
            aria-label="Expand the sidebar"
            aria-expanded={false}
            className="grid size-9 place-items-center rounded-[10px] text-muted-foreground transition-colors hover:bg-[rgba(var(--shadow-rgb),.06)] hover:text-text [&_svg]:size-[18px]"
          >
            <PanelLeftOpen />
          </button>
        </Hint>
        <RailLink href={home} label="New chat" active={pathname === home}>
          <SquarePen className="text-brand" />
        </RailLink>
        {questionsHref && (
          <RailLink href={questionsHref} label="Questions for you" dot={pendingQuestions > 0}>
            <Inbox />
          </RailLink>
        )}
        <RailLink href={knowledgeHref} label="Knowledge" active={pathname.startsWith(knowledgeHref)}>
          <BookOpen />
        </RailLink>
        <div className="flex-1" />
        <RailLink href={settingsHref} label="Settings" active={pathname.startsWith(settingsHref)}>
          <Settings />
        </RailLink>
        <span
          aria-hidden="true"
          className="mt-1 grid size-[30px] place-items-center rounded-full bg-brand-soft text-[12px] font-semibold text-brand-ink"
        >
          {who}
        </span>
      </nav>
    );
  }

  return (
    <nav
      className={cn(
        "flex h-full flex-col gap-1 bg-sidebar px-3 py-3.5",
        inSheet ? "w-full" : "w-[268px]",
      )}
      aria-label="Chats"
    >
      <div className="flex items-center justify-between px-1 pt-0.5 pb-2.5">
        <Link
          href={home}
          onClick={() => onNavigate?.()}
          className="flex items-center gap-2.5 rounded-sm text-brand"
          aria-label="Charie home"
        >
          <BrandMark className="size-7" />
          <Wordmark />
        </Link>
        {!inSheet && (
          <Hint label="Hide sidebar">
            <button
              type="button"
              onClick={toggleCollapsed}
              aria-label="Collapse the sidebar"
              aria-expanded
              className="grid size-8 place-items-center rounded-sm text-muted-foreground transition-colors hover:bg-surface-2 hover:text-text [&_svg]:size-[17px]"
            >
              <PanelLeftClose />
            </button>
          </Hint>
        )}
      </div>

      <Link
        href={home}
        onClick={() => onNavigate?.()}
        className="flex items-center gap-2.5 rounded-xl border border-border bg-surface px-3 py-[9px] text-[14px] font-medium shadow-[0_1px_2px_rgba(var(--shadow-rgb),.05)] transition-[box-shadow,transform] hover:-translate-y-px hover:shadow-[0_6px_16px_rgba(var(--shadow-rgb),.08)]"
      >
        <SquarePen aria-hidden="true" className="size-[17px] text-brand" />
        New chat
        <span className="sr-only"> — ask a fresh question</span>
      </Link>

      <div className="mt-2 grid gap-0.5">
        {questionsHref && (
          <NavItem
            href={questionsHref}
            icon={<Inbox />}
            label="Questions for you"
            badge={pendingQuestions}
            active={false}
            onNavigate={onNavigate}
          />
        )}
        <NavItem
          href={knowledgeHref}
          icon={<BookOpen />}
          label="Knowledge"
          active={pathname.startsWith(knowledgeHref)}
          onNavigate={onNavigate}
        />
      </div>

      <div className="-mx-1 mt-2.5 min-h-0 flex-1 overflow-y-auto px-1">
        {/* `null` is "not asked yet" and `[]` is "there is nothing". */}
        {conversations === null && !error && <SkeletonList rows={4} label="Loading your chats" />}
        {conversations?.length === 0 && (
          <p className="px-3 py-2 text-[13px] leading-relaxed text-muted-foreground">
            No chats yet. Ask something to start one.
          </p>
        )}
        {error && <p className="px-3 py-2 text-[13px] text-bad-ink">{error}</p>}

        {groups.map((group, groupIndex) => (
          <div key={group.label} className="grid grid-cols-[minmax(0,1fr)] gap-px">
            <p
              className={cn(
                "mx-3 mb-1 text-[11.5px] font-medium text-muted-foreground",
                groupIndex === 0 ? "mt-1" : "mt-3.5",
              )}
            >
              {group.label}
            </p>
            {group.items.map((conversation) => {
              const href = `/orgs/${orgId}/conversations/${conversation.id}`;
              const current = pathname === href;
              const label = threadLabel(conversation);

              if (renaming === conversation.id) {
                return (
                  <div key={conversation.id} className="px-0.5 py-0.5">
                    <input
                      className="h-8 w-full rounded-sm border border-brand bg-surface px-2.5 text-[13.5px] outline-none ring-[3px] ring-brand-soft"
                      aria-label="Chat title"
                      value={draft}
                      maxLength={300}
                      autoFocus
                      disabled={busy === conversation.id}
                      onChange={(event) => setDraft(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") void rename(conversation.id);
                        if (event.key === "Escape") setRenaming(null);
                      }}
                      onBlur={() => void rename(conversation.id)}
                    />
                  </div>
                );
              }

              if (confirming === conversation.id) {
                return (
                  <div
                    key={conversation.id}
                    className="my-1 grid gap-2.5 rounded-md border border-border bg-surface p-3 shadow-[0_6px_16px_rgba(var(--shadow-rgb),.08)]"
                  >
                    <p className="text-[13px] leading-relaxed text-text-2">
                      Archive “{label}”? Its answers and traces are kept, and you can bring it back.
                    </p>
                    <div className="flex gap-2">
                      <Button
                        variant="primary"
                        size="sm"
                        disabled={busy === conversation.id}
                        onClick={() => void archive(conversation.id)}
                      >
                        Archive
                      </Button>
                      <Button
                        size="sm"
                        disabled={busy === conversation.id}
                        onClick={() => setConfirming(null)}
                      >
                        Cancel
                      </Button>
                    </div>
                  </div>
                );
              }

              return (
                <div
                  key={conversation.id}
                  className={cn(
                    "group relative flex items-center rounded-[10px] transition-colors hover:bg-[rgba(var(--shadow-rgb),.05)]",
                    current && "bg-surface shadow-[0_1px_2px_rgba(var(--shadow-rgb),.07)] hover:bg-surface",
                  )}
                >
                  <Link
                    href={href}
                    onClick={() => onNavigate?.()}
                    aria-current={current ? "page" : undefined}
                    title={label}
                    className={cn(
                      "block min-w-0 flex-1 truncate rounded-[10px] px-3 py-[7px] text-[13.5px] text-text-2",
                      current && "font-medium text-text",
                    )}
                  >
                    {label}
                  </Link>
                  <div className="absolute right-1 flex items-center gap-0.5 rounded-sm bg-inherit opacity-0 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100">
                    <button
                      type="button"
                      className="grid size-6 place-items-center rounded-[7px] text-muted-foreground hover:bg-surface-2 hover:text-text"
                      onClick={() => {
                        setDraft(conversation.title ?? "");
                        setRenaming(conversation.id);
                      }}
                      aria-label={`Rename ${label}`}
                      title="Rename"
                    >
                      <Pencil aria-hidden="true" className="size-3.5" />
                    </button>
                    <button
                      type="button"
                      className="grid size-6 place-items-center rounded-[7px] text-muted-foreground hover:bg-surface-2 hover:text-text"
                      onClick={() => setConfirming(conversation.id)}
                      aria-label={`Archive ${label}`}
                      title="Archive"
                    >
                      <Archive aria-hidden="true" className="size-3.5" />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        ))}
      </div>

      <div className="grid gap-0.5 border-t border-border pt-2">
        <NavItem
          href={settingsHref}
          icon={<Settings />}
          label="Settings"
          active={pathname.startsWith(settingsHref)}
          onNavigate={onNavigate}
        />
        <div className="flex items-center gap-2.5 px-2.5 pt-2 pb-0.5">
          <span
            aria-hidden="true"
            className="grid size-[30px] shrink-0 place-items-center rounded-full bg-brand-soft text-[13px] font-semibold text-brand-ink"
          >
            {who}
          </span>
          <div className="min-w-0">
            <p className="truncate text-[13.5px] font-semibold">
              {person ? personLabel(person, session.who ?? "Signed in") : (session.who ?? "Signed in")}
            </p>
            <p className="truncate text-[12px] text-muted-foreground">
              {orgName ?? "Your organization"}
            </p>
          </div>
        </div>
      </div>
    </nav>
  );
}
