import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";
import type { KbChange } from "@charie/shared";
import { ReviewChangesDialog } from "./ReviewChangesDialog";

afterEach(cleanup);

const ADDED: KbChange = {
  key: "rule.refunds_out_of_sales",
  title: "Refunds come out of sales",
  change: "added",
  before: null,
  after: {
    key: "rule.refunds_out_of_sales",
    kind: "rule",
    name: "Refunds come out of sales",
    confidence: "doc",
    used: 0,
    short: "Refunds come out of sales.",
    meaning: "Refunds come out of sales; they are not separate income.",
  },
  reason: "Found in Refund policy.docx.",
  is_big: false,
};

const CHANGED: KbChange = {
  key: "default.lunch",
  title: "Lunch",
  change: "changed",
  before: {
    key: "default.lunch",
    kind: "word",
    name: "Lunch",
    confidence: "guess",
    used: 12,
    short: "The midday meal.",
    meaning: "The midday meal.",
  },
  after: {
    key: "default.lunch",
    kind: "word",
    name: "Lunch",
    confidence: "owner",
    used: 12,
    short: "Orders placed between 11 am and 2:30 pm.",
    meaning: "Orders placed between 11 am and 2:30 pm.",
  },
  reason: "The autumn menu guide says lunch ends at 2:30 pm.",
  is_big: true,
};

const REMOVED: KbChange = {
  key: "data_problem.late_orders",
  title: "Late orders from 3 restaurants",
  change: "removed",
  before: {
    key: "data_problem.late_orders",
    kind: "problem",
    name: "Late orders from 3 restaurants",
    confidence: "doc",
    used: 1,
    short: "Late orders arrived a day late.",
  },
  after: null,
  reason: "The late orders arrived. The data is complete now.",
  is_big: false,
};

function renderDialog(changes: KbChange[], isDraft: boolean) {
  const onPublish = vi.fn();
  const onClose = vi.fn();
  render(
    <ReviewChangesDialog
      versionNumber={15}
      changes={changes}
      isDraft={isDraft}
      onClose={onClose}
      onPublish={onPublish}
    />,
  );
  return { onPublish, onClose };
}

describe("ReviewChangesDialog", () => {
  test("shows old and new side by side", async () => {
    const user = userEvent.setup();
    const { onPublish } = renderDialog([REMOVED, ADDED, CHANGED], true);
    expect(screen.getByText("Changes in version 15")).not.toBeNull();
    // Added first, then changed, then removed.
    const titles = screen.getAllByText(/Refunds come out of sales|Lunch|Late orders from 3 restaurants/);
    expect(titles[0].textContent).toBe("Refunds come out of sales");
    // Changed entry: old on the left, new on the right.
    expect(screen.getAllByText("Version 14")).toHaveLength(3);
    expect(screen.getAllByText("Version 15")).toHaveLength(3);
    expect(screen.getByText("The midday meal.")).not.toBeNull();
    expect(screen.getAllByText("Orders placed between 11 am and 2:30 pm.").length).toBeGreaterThan(0);
    // Added entry: the old side is empty; removed entry: the new side is.
    expect(screen.getAllByText("Not in this version")).toHaveLength(2);
    expect(screen.getByText("Why: The autumn menu guide says lunch ends at 2:30 pm.")).not.toBeNull();
    await user.click(screen.getByRole("button", { name: "Publish version 15" }));
    expect(onPublish).toHaveBeenCalled();
    expect(screen.getAllByRole("button", { name: "Close" })).toHaveLength(2);
  });

  test("marks the big change", () => {
    renderDialog([CHANGED], true);
    expect(screen.getByText("Big change")).not.toBeNull();
    expect(screen.getByText("Changed")).not.toBeNull();
  });

  test("no changes explains itself, and old versions cannot publish", () => {
    const { onPublish } = renderDialog([], false);
    expect(screen.getByText("No changes to show.")).not.toBeNull();
    expect(screen.queryByRole("button", { name: /Publish version/ })).toBeNull();
    expect(onPublish).not.toHaveBeenCalled();
  });
});
