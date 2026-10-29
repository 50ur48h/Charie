import { useNavigate } from "react-router";
import { RefreshCw } from "lucide-react";
import {
  Button,
  IconBox,
  toast,
  useDocuments,
  useLearning,
  useRefreshLearning,
} from "@charie/shared";
import { countNewDocuments } from "../layout/useLearnerBadges";

// The "new documents since the last learning" banner (P04.4). Hidden when
// nothing is new. Refresh starts a refresh run, unless one is already going —
// then it just opens Learning, since that run already reads the new files.
export function RefreshBanner() {
  const navigate = useNavigate();
  const documents = useDocuments();
  const learning = useLearning();
  const refresh = useRefreshLearning();

  const count = countNewDocuments(documents.data?.documents ?? []);
  const live = (learning.data?.runs ?? [])[0];
  const running = live?.status === "running" || live?.status === "paused";

  if (documents.isPending || learning.isPending) return null;
  if (documents.isError || learning.isError) return null;
  if (count === 0) return null;

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
        <b className="block text-text">
          {count === 1 ? "1 new document since the last learning" : `${count} new documents since the last learning`}
        </b>
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
