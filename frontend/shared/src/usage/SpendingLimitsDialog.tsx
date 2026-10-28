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

// Spending limits dialog (architecture 09 PATCH /api/settings). The server
// validates; the screen shows its error message. Shared by the banner and
// the Usage page so both manage the same limits.
export function SpendingLimitsDialog({
  limitUsd,
  warnPercent,
  saving = false,
  serverError = null,
  onSave,
  onClose,
}: {
  limitUsd: number;
  warnPercent: number;
  saving?: boolean;
  serverError?: string | null;
  onSave: (patch: { spend_limit_usd?: number; spend_warn_percent?: number }) => void;
  onClose: () => void;
}) {
  const [limit, setLimit] = useState(String(limitUsd));
  const [warn, setWarn] = useState(String(warnPercent));
  const [blank, setBlank] = useState<string | null>(null);

  function save(): void {
    const limitNum = Number(limit);
    if (limit.trim() === "" || !Number.isFinite(limitNum) || limitNum <= 0) {
      setBlank("The monthly credit must be more than $0.");
      return;
    }
    const warnNum = Number(warn);
    if (warn.trim() === "" || !Number.isInteger(warnNum) || warnNum < 1 || warnNum > 99) {
      setBlank("The warning level must be between 1 and 99 percent.");
      return;
    }
    setBlank(null);
    onSave({ spend_limit_usd: limitNum, spend_warn_percent: warnNum });
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
