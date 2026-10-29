import { History } from "lucide-react";
import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  Pill,
  type KbVersion,
} from "@charie/shared";
import { shortDate } from "../lib/when";

const MADE_BY: Record<KbVersion["made_by"], string> = {
  first_learning: "First learning",
  refresh: "Refresh",
  nightly: "Nightly check",
  owner_edit: "Your changes",
};

// Versions (P04.9): every version and what changed in each, newest first.
// Charie answers with the live one.
export function VersionsButton({ onOpen }: { onOpen: () => void }) {
  return (
    <Button variant="outline" onClick={onOpen}>
      <History aria-hidden="true" className="[--icon:16px]" />
      Versions
    </Button>
  );
}

export function VersionsDialog({
  versions,
  onClose,
  onSeeChanges,
}: {
  versions: KbVersion[];
  onClose: () => void;
  onSeeChanges: (versionNumber: number) => void;
}) {
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent aria-label="Versions">
        <DialogTitle>Versions</DialogTitle>
        <DialogDescription>
          Every version of Charie&apos;s knowledge. Charie answers with the live one.
        </DialogDescription>
        <ul className="mt-4 grid max-h-[60vh] gap-2 overflow-y-auto pr-1">
          {versions.map((version) => (
            <li
              key={version.id}
              className="rounded-[12px] border border-border p-[12px_14px]"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[14px] font-semibold">Version {version.number}</span>
                {version.status === "draft" && <Pill tone="warn">Draft</Pill>}
                {version.status === "published" && <Pill tone="good">Live</Pill>}
                {version.status === "archived" && <Pill>Older</Pill>}
                <span className="text-[12.5px] text-muted">
                  {MADE_BY[version.made_by]} ·{" "}
                  {shortDate(
                    version.status === "draft"
                      ? version.created_at
                      : (version.published_at ?? version.created_at),
                  )}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  className="ml-auto"
                  onClick={() => onSeeChanges(version.number)}
                >
                  See changes
                </Button>
              </div>
              <p className="mt-1 text-[13.5px] text-text-2">{version.summary.note}</p>
            </li>
          ))}
        </ul>
      </DialogContent>
    </Dialog>
  );
}
