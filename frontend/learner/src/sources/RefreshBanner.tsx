import { useNavigate } from "react-router";
import { RefreshCw } from "lucide-react";
import { Button, IconBox, toast, useLearning, useRefreshLearning, useRefreshStatus } from "@charie/shared";

// The refresh banner. The snapshot-based pending changes decide: hidden
// when nothing is pending, so removals show and failed runs keep pending.
// Refresh starts a refresh run, unless one is already going — then it just
// opens Learning, since that run already reads the changes.
export function RefreshBanner() {
  const navigate = useNavigate();
  const learning = useLearning();
  const runs = learning.data?.runs ?? [];
  const live = runs[0];
  const running = live?.status === "running" || live?.status === "paused";
  const status = useRefreshStatus(running);
  const refresh = useRefreshLearning();

  if (learning.isPending || status.isPending) return null;
  if (learning.isError || status.isError) return null;
  const added = status.data?.documents.length ?? 0;
  const removed = status.data?.removed.length ?? 0;
  const notesChanged = status.data?.notes_changed ?? false;
  if (added === 0 && removed === 0 && !notesChanged) return null;

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
    <div className="mb-[22px] flex flex-wrap items-center gap-3.5 rounded-[16px] bg-accent-soft p-[16px_20px]">
      <IconBox icon={RefreshCw} tone="accent" size={40} />
      <div className="min-w-0 flex-1">
        <b className="block text-text">{bannerTitle(added, removed, notesChanged)}</b>
        <span className="text-[13px] text-accent-ink">
          Charie keeps using what it knows now until the refresh is done. Only the changes are
          learned.
        </span>
      </div>
      <Button disabled={refresh.isPending} onClick={onRefresh} className="ml-auto flex-none max-[640px]:ml-0 max-[640px]:w-full">
        <RefreshCw aria-hidden="true" className="[--icon:16px]" />
        {refresh.isPending ? "Refreshing…" : "Refresh knowledge base"}
      </Button>
    </div>
  );
}

function plural(count: number, word: string): string {
  return count === 1 ? `1 ${word}` : `${count} ${word}s`;
}

// One line for every mix of new, removed and changed notes.
function bannerTitle(added: number, removed: number, notesChanged: boolean): string {
  if (added === 0 && removed === 0) return "Your notes changed since the last learning";
  const what =
    added > 0 && removed > 0
      ? plural(added + removed, "changed document")
      : added > 0
        ? plural(added, "new document")
        : plural(removed, "removed document");
  const tail = notesChanged
    ? " and changed notes since the last learning"
    : " since the last learning";
  return `${what}${tail}`;
}
