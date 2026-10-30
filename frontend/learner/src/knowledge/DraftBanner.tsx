import { Layers } from "lucide-react";
import { Button, IconBox } from "@charie/shared";
import type { KnowledgeVersion } from "@charie/shared";

// The draft banner (P04.8): which draft is open, how many changes it has,
// and that the live version stays live until publish. Hidden with no draft.
// The version comes from the knowledge list, so the banner works in mock
// mode and on real data; review, versions and publish stay mock-only
// until P09.9, and their buttons show the API's error on real data.
export function DraftBanner({
  version,
  liveNumber,
  onReview,
  onPublish,
}: {
  version: KnowledgeVersion | null;
  liveNumber: number | null;
  onReview: () => void;
  onPublish: () => void;
}) {
  if (version === null || version.status !== "draft") return null;
  return (
    <div className="mb-[18px] flex flex-wrap items-center gap-3.5 rounded-[16px] bg-warn-soft p-[14px_18px]">
      <IconBox icon={Layers} tone="warn" size={40} />
      <div className="min-w-0 flex-1 basis-[220px]">
        <b className="block text-text">
          Draft version {version.number} has {version.changes === 1 ? "1 change" : `${version.changes} changes`}
        </b>
        <span className="text-[13px] text-warn-ink">
          {version.summary.note}
          {liveNumber !== null ? `. Version ${liveNumber} stays live until you publish.` : ""}
        </span>
      </div>
      <span className="ml-auto inline-flex flex-none flex-wrap gap-2 max-[640px]:ml-0 max-[640px]:w-full max-[640px]:*:flex-1">
        <Button variant="outline" size="sm" onClick={onReview}>
          Review changes
        </Button>
        <Button size="sm" onClick={onPublish}>
          Publish version {version.number}
        </Button>
      </span>
    </div>
  );
}
