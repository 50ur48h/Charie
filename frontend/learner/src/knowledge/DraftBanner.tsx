import { Layers } from "lucide-react";
import { Button, IconBox, useVersions } from "@charie/shared";

// The draft banner (P04.8): which draft is open, how many changes it has,
// and that the live version stays live until publish. Hidden with no draft.
export function DraftBanner({
  onReview,
  onPublish,
}: {
  onReview: () => void;
  onPublish: () => void;
}) {
  const versions = useVersions();
  if (versions.isPending || versions.isError) return null;
  const list = versions.data?.versions ?? [];
  const draft = list.find((version) => version.status === "draft");
  if (!draft) return null;
  const live = list.find((version) => version.status === "published");
  const total = draft.summary.added + draft.summary.changed + draft.summary.removed;
  return (
    <div className="mb-[18px] flex flex-wrap items-center gap-3.5 rounded-[16px] bg-warn-soft p-[14px_18px]">
      <IconBox icon={Layers} tone="warn" size={40} />
      <div className="min-w-0 flex-1 basis-[220px]">
        <b className="block text-text">
          Draft version {draft.number} has {total === 1 ? "1 change" : `${total} changes`}
        </b>
        <span className="text-[13px] text-warn-ink">
          {draft.summary.note}
          {live ? `. Version ${live.number} stays live until you publish.` : ""}
        </span>
      </div>
      <span className="ml-auto inline-flex flex-none flex-wrap gap-2 max-[640px]:ml-0 max-[640px]:w-full max-[640px]:*:flex-1">
        <Button variant="outline" size="sm" onClick={onReview}>
          Review changes
        </Button>
        <Button size="sm" onClick={onPublish}>
          Publish version {draft.number}
        </Button>
      </span>
    </div>
  );
}
