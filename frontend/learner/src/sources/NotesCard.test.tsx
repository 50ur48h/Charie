import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import type { OwnerNotes } from "@charie/shared";
import { NotesCard } from "./NotesCard";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const SORTED = {
  hard_rules: [{ key: "rule.usd_only", title: "Money is always in US dollars. Never convert." }],
  style: [{ key: "style.direct", title: "Start with the direct answer." }],
  hints: [{ key: "default.delivery_fees", title: "Delivery fees are part of the order total." }],
};

function renderCard(notes: OwnerNotes) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string) => {
      if (url.includes("/api/owner-notes")) return Promise.resolve(json(notes));
      return Promise.resolve(json({}));
    }),
  );
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <NotesCard />
    </QueryClientProvider>,
  );
}

describe("NotesCard", () => {
  test("shows the 3 columns like the design", async () => {
    renderCard({
      text: "# Notes for Charie\nNever convert currencies.",
      saved_at: "2026-10-03T10:00:00+05:30",
      lines: 2,
      sorted: SORTED,
      sorted_at: "2026-10-03T10:00:00+05:30",
    });
    expect(await screen.findByText("Owner notes.md")).toBeTruthy();
    expect(screen.getByText("Updated 3 Oct · 2 lines")).toBeTruthy();
    expect(screen.getByText("Hard rules")).toBeTruthy();
    expect(screen.getByText("Style")).toBeTruthy();
    expect(screen.getByText("Hints about the data")).toBeTruthy();
    expect(screen.getByText("Money is always in US dollars. Never convert.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Edit notes" })).toBeTruthy();
  });

  test("shows the empty state with Add notes", async () => {
    renderCard({ text: "", saved_at: null, lines: 0, sorted: null, sorted_at: null });
    expect(await screen.findByText("Owner notes.md")).toBeTruthy();
    expect(screen.getByText(/No notes yet/)).toBeTruthy();
    expect(screen.queryByText("Hard rules")).toBeNull();
    expect(screen.getByRole("button", { name: "Add notes" })).toBeTruthy();
  });

  test("says when notes changed after sorting", async () => {
    renderCard({
      text: "# Notes\nOld.\nNew rule.",
      saved_at: "2026-10-27T21:00:00+05:30",
      lines: 3,
      sorted: SORTED,
      sorted_at: "2026-10-03T10:00:00+05:30",
    });
    expect(
      await screen.findByText("You changed your notes. Charie sorts them again when it next learns."),
    ).toBeTruthy();
    expect(screen.getByText("Money is always in US dollars. Never convert.")).toBeTruthy();
  });

  test("editing opens the dialog", async () => {
    renderCard({
      text: "# Notes\nOld.",
      saved_at: "2026-10-03T10:00:00+05:30",
      lines: 2,
      sorted: SORTED,
      sorted_at: "2026-10-03T10:00:00+05:30",
    });
    fireEvent.click(await screen.findByRole("button", { name: "Edit notes" }));
    expect(await screen.findByText("Your notes")).toBeTruthy();
  });

  test("an empty column states it has nothing to sort yet", async () => {
    renderCard({
      text: "# Notes\nOld.",
      saved_at: "2026-10-03T10:00:00+05:30",
      lines: 2,
      sorted: { ...SORTED, hints: [] },
      sorted_at: "2026-10-03T10:00:00+05:30",
    });
    expect(await screen.findByText("Charie sorts your notes when it learns.")).toBeTruthy();
    expect(screen.getByText(
      "Money is always in US dollars. Never convert.",
    )).toBeTruthy();
  });

  test("counts many lines", async () => {
    const text = Array.from({ length: 42 }, (_, index) => `Rule ${index + 1}.`).join("\n");
    renderCard({
      text,
      saved_at: "2026-10-03T10:00:00+05:30",
      lines: 42,
      sorted: null,
      sorted_at: null,
    });
    expect(await screen.findByText("Updated 3 Oct · 42 lines")).toBeTruthy();
  });
});
