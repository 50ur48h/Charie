import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";
import type { KbVersion } from "@charie/shared";
import { VersionsDialog } from "./VersionsDialog";

afterEach(cleanup);

const VERSIONS: KbVersion[] = [
  {
    id: 15,
    number: 15,
    status: "draft",
    made_by: "refresh",
    created_at: "2026-10-27T21:12:00+05:30",
    published_at: null,
    summary: { added: 3, changed: 2, removed: 1, note: "3 new facts from new documents" },
  },
  {
    id: 14,
    number: 14,
    status: "published",
    made_by: "nightly",
    created_at: "2026-10-20T02:00:00+05:30",
    published_at: "2026-10-20T02:06:00+05:30",
    summary: { added: 2, changed: 0, removed: 0, note: "2 new coupon codes, 1 new restaurant" },
  },
  {
    id: 13,
    number: 13,
    status: "archived",
    made_by: "owner_edit",
    created_at: "2026-10-16T10:00:00+05:30",
    published_at: "2026-10-16T10:00:00+05:30",
    summary: { added: 0, changed: 0, removed: 0, note: "Your answers to 12 questions" },
  },
];

describe("VersionsDialog", () => {
  test("lists versions newest first, with Live and Draft", async () => {
    const user = userEvent.setup();
    const onSeeChanges = vi.fn();
    render(<VersionsDialog versions={VERSIONS} onClose={vi.fn()} onSeeChanges={onSeeChanges} />);
    const rows = screen.getAllByRole("button", { name: "See changes" });
    expect(rows).toHaveLength(3);
    const items = screen.getAllByText(/Version \d+/);
    expect(items.map((item) => item.textContent)).toEqual(["Version 15", "Version 14", "Version 13"]);
    expect(screen.getByText("Draft")).not.toBeNull();
    expect(screen.getByText("Live")).not.toBeNull();
    expect(screen.getByText("Older")).not.toBeNull();
    expect(screen.getByText(/Refresh/)).not.toBeNull();
    expect(screen.getByText("2 new coupon codes, 1 new restaurant")).not.toBeNull();
    await user.click(rows[0]);
    expect(onSeeChanges).toHaveBeenCalledWith(15);
  });
});
