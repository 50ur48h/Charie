import { useState } from "react";
import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
  Input,
  Field,
  toast,
  useChangePassword,
  ApiError,
} from "@charie/shared";

// Change password dialog (P05.4 POST /api/password { current, new }).
// A mismatch between the two new passwords is shown before anything is sent;
// a wrong current password or a short new one shows the API's message on the
// field it belongs to.
type FieldName = "current" | "next" | "confirm";

export function ChangePasswordDialog({ onClose }: { onClose: () => void }) {
  const change = useChangePassword();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [problem, setProblem] = useState<{ field: FieldName | null; message: string } | null>(null);

  function fieldError(field: FieldName): string | undefined {
    return problem?.field === field ? problem.message : undefined;
  }

  function save(): void {
    if (next !== confirm) {
      setProblem({ field: "confirm", message: "The new passwords don't match." });
      return;
    }
    setProblem(null);
    change.mutate(
      { current, next },
      {
        onSuccess: () => {
          toast("Password changed.");
          onClose();
        },
        onError: (error) => {
          const field: FieldName | null =
            error instanceof ApiError && error.code === "wrong_password"
              ? "current"
              : error instanceof ApiError && error.code === "password_too_short"
                ? "next"
                : null;
          setProblem({ field, message: error.message });
        },
      },
    );
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent aria-label="Change password">
        <DialogTitle>Change password</DialogTitle>
        <DialogDescription>One shared password for Charie.</DialogDescription>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            save();
          }}
        >
          <div className="grid gap-3">
            <Field label="Current password" htmlFor="password-current" error={fieldError("current")}>
              <Input
                id="password-current"
                type="password"
                autoComplete="current-password"
                value={current}
                onChange={(event) => {
                  setCurrent(event.target.value);
                  setProblem(null);
                }}
              />
            </Field>
            <Field label="New password" htmlFor="password-new" error={fieldError("next")}>
              <Input
                id="password-new"
                type="password"
                autoComplete="new-password"
                value={next}
                onChange={(event) => {
                  setNext(event.target.value);
                  setProblem(null);
                }}
              />
            </Field>
            <Field
              label="Confirm new password"
              htmlFor="password-confirm"
              error={fieldError("confirm")}
            >
              <Input
                id="password-confirm"
                type="password"
                autoComplete="new-password"
                value={confirm}
                onChange={(event) => {
                  setConfirm(event.target.value);
                  setProblem(null);
                }}
              />
            </Field>
          </div>
          {problem && (
            <p role="alert" className="mt-2 text-[13px] text-bad-ink">
              {problem.message}
            </p>
          )}
          <DialogFooter>
            <Button variant="ghost" type="button" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={change.isPending}>
              {change.isPending ? "Changing…" : "Change password"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
