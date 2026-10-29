import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";
import { MarkWrongDialog } from "./MarkWrongDialog";

afterEach(cleanup);

describe("MarkWrongDialog", () => {
  test("sends the note", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    render(<MarkWrongDialog entryName="Lunch" onSave={onSave} onClose={vi.fn()} />);
    await user.type(
      screen.getByLabelText("What is wrong?"),
      "lunch ends at 2:30 pm, not 3 pm.",
    );
    await user.click(screen.getByRole("button", { name: "Mark as wrong" }));
    expect(onSave).toHaveBeenCalledWith("lunch ends at 2:30 pm, not 3 pm.");
  });

  test("works with no note", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    render(<MarkWrongDialog entryName="Lunch" onSave={onSave} onClose={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Mark as wrong" }));
    expect(onSave).toHaveBeenCalledWith(null);
  });
});
