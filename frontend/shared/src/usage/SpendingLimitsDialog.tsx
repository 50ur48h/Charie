import { useState } from "react";
import { Button } from "../components/Button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
} from "../components/Dialog";
import { Field } from "../components/Input";
import { Input } from "../components/Input";
import { nextLimit, validateLimit, validateWarn } from "../api/spending";

// Spending limits dialog (architecture 09 PATCH /api/settings). The server
// validates; the screen shows its error message. Shared by the banner and
// the Usage page so both manage the same limits. When paused, one click
// raises straight to nextLimit and saves the warning level with it.
export function SpendingLimitsDialog({
  limitUsd,
  warnPercent,
  spentUsd,
  paused = false,
  saving = false,
  serverError = null,
  onSave,
  onClose,
}: {
  limitUsd: number;
  warnPercent: number;
  spentUsd?: number;
  paused?: boolean;
  saving?: boolean;
  serverError?: string | null;
  onSave: (patch: { spend_limit_usd?: number; spend_warn_percent?: number }) => void;
  onClose: () => void;
}) {
  const [limit, setLimit] = useState(String(limitUsd));
  const [warn, setWarn] = useState(String(warnPercent));
  const [blank, setBlank] = useState<string | null>(null);

  function save(): void {
    const limitError = validateLimit(limit);
    if (limitError) {
      setBlank(limitError);
      return;
    }
    const warnError = validateWarn(warn);
    if (warnError) {
      setBlank(warnError);
      return;
    }
    setBlank(null);
    onSave({ spend_limit_usd: Number(limit), spend_warn_percent: Number(warn) });
  }

  function raise(): void {
    const warnError = validateWarn(warn);
    if (warnError) {
      setBlank(warnError);
      return;
    }
    setBlank(null);
    onSave({
      spend_limit_usd: nextLimit(spentUsd ?? limitUsd),
      spend_warn_percent: Number(warn),
    });
  }

  const error = blank ?? serverError;
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent aria-label="Spending limits">
        <DialogTitle>Spending limits</DialogTitle>
        <DialogDescription>
          Charie stops new questions when the month&apos;s credit is used up. The warning shows
          first, at your warning level.
        </DialogDescription>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            save();
          }}
        >
          <div className="grid gap-3">
            <Field label="Monthly credit (USD)" htmlFor="spend-limit" error={error ?? undefined}>
              <Input
                id="spend-limit"
                inputMode="decimal"
                value={limit}
                onChange={(event) => {
                  setLimit(event.target.value);
                  setBlank(null);
                }}
                aria-invalid={error ? true : undefined}
              />
            </Field>
            <Field
              label="Warn me at (percent)"
              htmlFor="spend-warn"
              error={error ?? undefined}
            >
              <Input
                id="spend-warn"
                inputMode="numeric"
                value={warn}
                onChange={(event) => {
                  setWarn(event.target.value);
                  setBlank(null);
                }}
                aria-invalid={error ? true : undefined}
              />
            </Field>
          </div>
          {error && (
            <p role="alert" className="mt-2 text-[13px] text-bad-ink">
              {error}
            </p>
          )}
          <DialogFooter>
            {paused && spentUsd !== undefined && (
              <Button type="button" disabled={saving} onClick={raise}>
                Raise limit to ${nextLimit(spentUsd)}
              </Button>
            )}
            <Button variant="ghost" type="button" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={saving}>
              {saving ? "Saving…" : "Save limits"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
