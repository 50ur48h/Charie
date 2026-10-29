import { useNavigate } from "react-router";
import { RefreshCw } from "lucide-react";
import {
  Button,
  IconBox,
  toast,
  useDocuments,
  useLearning,
  useOwnerNotes,
  useRefreshLearning,
} from "@charie/shared";
import { countNewDocuments } from "../layout/useLearnerBadges";

// The refresh banner (P04.4 documents, P04.6 notes). Hidden when nothing
// is new. Refresh starts a refresh run, unless one is already going —
// then it just opens Learning, since that run already reads the changes.
export function RefreshBanner() {
  const navigate = useNavigate();
  const documents = useDocuments();
  const learning = useLearning();
  const notes = useOwnerNotes();
  const refresh = useRefreshLearning();

  const count = countNewDocuments(documents.data?.documents ?? []);
  const runs = learning.data?.runs ?? [];
  const live = runs[0];
  const running = live?.status === "running" || live?.status === "paused";
  const notesChanged = notesChangedSinceRun(
    notes.data?.saved_at ?? null,
    runs[0]?.started_at ?? null,
  );

  if (documents.isPending || learning.isPending || notes.isPending) return null;
  if (documents.isError || learning.isError || notes.isError) return null;
  if (count === 0 && !notesChanged) return null;

  const title =
    count > 0 && notesChanged
      ? `${count === 1 ? "1 new document" : `${count} new documents`} and changed notes since the last learning`
      : notesChanged
        ? "Your notes changed since the last learning"
        : count === 1
          ? "1 new document since the last learning"
          : `${count} new documents since the last learning`;

  function onRefresh(): void {
    if (running) {
      navigate("/learning");
      return;
    }
    refresh.mutate(undefined, {
      onSuccess: () => navigate("/learning"),
      onError: (error) => toast(error.message),
    });
  }

  return (
    <div className="mb-[22px] flex items-center gap-3.5 rounded-[16px] bg-accent-soft p-[16px_20px]">
      <IconBox icon={RefreshCw} tone="accent" size={40} />
      <div className="min-w-0 flex-1">
        <b className="block text-text">{title}</b>
        <span className="text-[13px] text-accent-ink">
          Charie keeps using what it knows now until the refresh is done. Only the changes are
          learned.
        </span>
      </div>
      <Button disabled={refresh.isPending} onClick={onRefresh} className="ml-auto flex-none">
        <RefreshCw aria-hidden="true" className="[--icon:16px]" />
        {refresh.isPending ? "Refreshing…" : "Refresh knowledge base"}
      </Button>
    </div>
  );
}

// Notes count as changed when saved after the newest run started, or when
// saved with no run yet (mirrors the mock's refresh reason).
export function notesChangedSinceRun(
  savedAt: string | null,
  newestRunStartedAt: string | null,
): boolean {
  if (!savedAt) return false;
  if (!newestRunStartedAt) return true;
  return Date.parse(savedAt) > Date.parse(newestRunStartedAt);
}
