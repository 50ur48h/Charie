"use client";

/**
 * Chats that were put away, and the way to bring them back (WP13.1b).
 *
 * **This screen is what makes the sidebar's promise true.** Archiving says the
 * thread can be restored, and before this existed there was nowhere to restore
 * it from — the old conversations list held the "Show archived" toggle and this
 * work package replaced that list with a sidebar. Shipping the sidebar without
 * this would have left a sentence in the product that the product could not
 * honour, which is precisely the defect class the archive-not-delete wording was
 * chosen to avoid.
 *
 * Every role may be here: these are your own threads, and a colleague's is a 404
 * even to an Admin (B-037).
 */

import { Archive, CircleAlert, MessagesSquare, RotateCcw } from "lucide-react";
import { AnimatePresence, MotionConfig, motion } from "motion/react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { SkeletonList } from "@/components/ui/skeleton";
import { ApiError, createApi, type Conversation } from "@/lib/api-client";
import { useSession } from "@/lib/auth/session";

function label(conversation: Conversation): string {
  const title = conversation.title?.trim();
  return title && title.length > 0 ? title : "Untitled chat";
}

const day = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", year: "numeric" });

/** When it was put away, which database it asked, and how much is in it — one quiet line. */
function details(conversation: Conversation): string {
  const parts: string[] = [];
  const archivedAt = conversation.archived_at ? new Date(conversation.archived_at) : null;
  if (archivedAt && !Number.isNaN(archivedAt.getTime())) {
    parts.push(`Archived ${day.format(archivedAt)}`);
  }
  if (conversation.data_source_name) parts.push(conversation.data_source_name);
  parts.push(
    conversation.message_count === 1 ? "1 message" : `${conversation.message_count} messages`,
  );
  return parts.join(" · ");
}

export function ArchivedChats({ orgId }: { orgId: string }) {
  const session = useSession();
  const api = useMemo(() => createApi(session.getToken), [session.getToken]);

  const [archived, setArchived] = useState<Conversation[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setArchived(await api.conversations(orgId, { archived: true }));
  }, [api, orgId]);

  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const threads = await api.conversations(orgId, { archived: true });
        if (alive) setArchived(threads);
      } catch (cause) {
        if (alive) {
          setError(
            cause instanceof ApiError ? cause.message : "Archived chats could not be loaded.",
          );
        }
      }
    })();
    return () => {
      alive = false;
    };
  }, [api, orgId]);

  const restore = useCallback(
    async (conversation: Conversation) => {
      setBusy(conversation.id);
      setError(null);
      try {
        await api.archiveConversation(orgId, conversation.id, false);
        await load();
        toast(`Restored “${label(conversation)}”`);
      } catch (cause) {
        setError(cause instanceof ApiError ? cause.message : "That chat could not be restored.");
      } finally {
        setBusy(null);
      }
    },
    [api, orgId, load],
  );

  return (
    <Card
      title="Archived chats"
      subtitle="Put away, not deleted — every answer and its trace is still here."
      action={
        archived && archived.length > 0 ? (
          <Badge className="tabular-nums">{archived.length}</Badge>
        ) : undefined
      }
    >
      {archived === null && !error && <SkeletonList rows={2} label="Loading archived chats" />}
      {archived?.length === 0 && (
        <EmptyState icon={<Archive />} title="Nothing archived" action={null}>
          Chats you put away appear here, with their answers and traces intact — and you can bring
          any of them back.
        </EmptyState>
      )}
      {error && (
        <p role="alert" className="mt-2 flex items-start gap-2 text-[13px] text-bad-ink">
          <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          {error}
        </p>
      )}

      {archived && archived.length > 0 && (
        <MotionConfig reducedMotion="user">
          <ul className="-my-1">
            <AnimatePresence initial={false}>
              {archived.map((conversation, index) => (
                <motion.li
                  key={conversation.id}
                  layout
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0, transition: { delay: index * 0.03 } }}
                  exit={{ opacity: 0, transition: { duration: 0.15 } }}
                  className="flex items-center gap-3 border-b border-border-soft py-3 last:border-b-0"
                >
                  <span
                    aria-hidden="true"
                    className="grid size-9 shrink-0 place-items-center rounded-md bg-surface-2 text-muted-foreground [&_svg]:size-[17px]"
                  >
                    <MessagesSquare />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[14px] font-medium text-text">
                      {label(conversation)}
                    </p>
                    <p className="truncate text-[12.5px] text-muted-foreground">
                      {details(conversation)}
                    </p>
                  </div>
                  <Button
                    size="sm"
                    disabled={busy === conversation.id}
                    onClick={() => void restore(conversation)}
                  >
                    <RotateCcw aria-hidden="true" />
                    {busy === conversation.id ? "Restoring…" : "Restore"}
                  </Button>
                </motion.li>
              ))}
            </AnimatePresence>
          </ul>
        </MotionConfig>
      )}
    </Card>
  );
}
