import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";
import { EntryEditForm } from "./EntryEditForm";

afterEach(cleanup);

describe("EntryEditForm", () => {
  test("saves the title and meaning", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    render(
      <EntryEditForm title="Lunch" meaning="Midday meal." onSave={onSave} onCancel={vi.fn()} />,
    );
    await user.clear(screen.getByLabelText("Title"));
    await user.type(screen.getByLabelText("Title"), "Lunch hours");
    await user.clear(screen.getByLabelText("Meaning"));
    await user.type(screen.getByLabelText("Meaning"), "Orders placed between 11 am and 2:30 pm.");
    await user.click(screen.getByRole("button", { name: "Save change" }));
    expect(onSave).toHaveBeenCalledWith({
      title: "Lunch hours",
      meaning: "Orders placed between 11 am and 2:30 pm.",
    });
  });

  test("cancel leaves the entry alone", async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();
    const onSave = vi.fn();
    render(
      <EntryEditForm title="Lunch" meaning="Midday meal." onSave={onSave} onCancel={onCancel} />,
    );
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalled();
    expect(onSave).not.toHaveBeenCalled();
  });

  test("blank title or meaning explains itself", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    render(
      <EntryEditForm title="Lunch" meaning="Midday meal." onSave={onSave} onCancel={vi.fn()} />,
    );
    await user.clear(screen.getByLabelText("Title"));
    await user.click(screen.getByRole("button", { name: "Save change" }));
    expect(screen.getByText("The entry still needs a title and a meaning.")).not.toBeNull();
    expect(onSave).not.toHaveBeenCalled();
  });
});
