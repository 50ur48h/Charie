import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
  Pill,
  type KbChange,
} from "@charie/shared";

const ORDER = ["added", "changed", "removed"] as const;

// Review changes (P04.9): old and new side by side, added first, then
// changed, then removed. The draft also offers Publish.
export function ReviewChangesDialog({
  versionNumber,
  changes,
  isDraft,
  publishing = false,
  onClose,
  onPublish,
}: {
  versionNumber: number;
  changes: KbChange[];
  isDraft: boolean;
  publishing?: boolean;
  onClose: () => void;
  onPublish: () => void;
}) {
  const ordered = [...changes].sort(
    (a, b) => ORDER.indexOf(a.change) - ORDER.indexOf(b.change),
  );
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent
        aria-label={`Changes in version ${versionNumber}`}
        className="max-w-[880px]"
      >
        <DialogTitle>Changes in version {versionNumber}</DialogTitle>
        <DialogDescription>Old on the left, new on the right.</DialogDescription>
        {ordered.length === 0 ? (
          <p className="py-4 text-[14px] text-muted">No changes to show.</p>
        ) : (
          <ul className="mt-4 grid max-h-[60vh] gap-3 overflow-y-auto pr-1">
            {ordered.map((change) => (
              <li
                key={change.key}
                className="rounded-[12px] border border-border p-[14px_16px]"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[14px] font-medium">{change.title}</span>
                  {change.change === "added" && <Pill tone="accent">New</Pill>}
                  {change.change === "changed" && <Pill>Changed</Pill>}
                  {change.change === "removed" && <Pill tone="bad">Removed</Pill>}
                  {change.is_big && <Pill tone="warn">Big change</Pill>}
                </div>
                <div className="mt-2.5 grid gap-2 sm:grid-cols-2">
                  <ChangeSide
                    label={`Version ${versionNumber - 1}`}
                    entry={change.before}
                  />
                  <ChangeSide label={`Version ${versionNumber}`} entry={change.after} />
                </div>
                <p className="mt-2 text-[13px] text-muted">Why: {change.reason}</p>
              </li>
            ))}
          </ul>
        )}
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            Close
          </Button>
          {isDraft && (
            <Button disabled={publishing} onClick={onPublish}>
              {publishing ? "Publishing…" : `Publish version ${versionNumber}`}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ChangeSide({
  label,
  entry,
}: {
  label: string;
  entry: KbChange["before"];
}) {
  return (
    <div className="rounded-[10px] bg-surface-2 p-[10px_12px]">
      <div className="text-[12px] font-semibold uppercase tracking-wide text-muted">{label}</div>
      {entry ? (
        <>
          <div className="mt-1 text-[13.5px] font-medium">{entry.name}</div>
          <div className="mt-0.5 text-[13px] text-text-2">{entry.meaning ?? entry.short}</div>
        </>
      ) : (
        <div className="mt-1 text-[13.5px] text-muted">Not in this version</div>
      )}
    </div>
  );
}
