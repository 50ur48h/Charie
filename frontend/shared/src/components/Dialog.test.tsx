import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";
import { useState } from "react";
import { Button } from "./Button";
import {
  ConfirmDialog,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from "./Dialog";

afterEach(cleanup);

function ConfirmHarness({ onConfirm }: { onConfirm: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button onClick={() => setOpen(true)}>Forget everything</Button>
      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title="Forget everything?"
        body="Charie forgets every preference you told it. This can't be undone."
        confirmLabel="Forget everything"
        tone="danger"
        onConfirm={onConfirm}
      />
    </>
  );
}

describe("Dialog", () => {
  test("ConfirmDialog calls onConfirm and closes", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(<ConfirmHarness onConfirm={onConfirm} />);
    await user.click(screen.getByRole("button", { name: "Forget everything" }));
    const dialog = screen.getByRole("dialog", { name: "Forget everything?" });
    await user.click(within(dialog).getByRole("button", { name: "Forget everything" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  test("Escape closes the dialog and focus goes back to the trigger", async () => {
    const user = userEvent.setup();
    render(
      <Dialog>
        <DialogTrigger asChild>
          <Button>Delete it</Button>
        </DialogTrigger>
        <DialogContent>
          <DialogTitle>Sure?</DialogTitle>
          <DialogDescription>This cannot be undone.</DialogDescription>
        </DialogContent>
      </Dialog>,
    );
    const trigger = screen.getByRole("button", { name: "Delete it" });
    await user.click(trigger);
    expect(screen.getByRole("dialog", { name: "Sure?" })).toBeTruthy();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });
});
