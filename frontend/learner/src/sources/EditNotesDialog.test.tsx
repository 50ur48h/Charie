import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";
import { Toaster } from "@charie/shared";
import { EditNotesDialog } from "./EditNotesDialog";

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

function renderDialog(putStatus = 200) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes("/api/owner-notes") && init?.method === "PUT") {
        if (putStatus !== 200) return Promise.resolve(json({ error: "x" }, putStatus));
        return Promise.resolve(
          json({ text: "x", saved_at: new Date().toISOString(), lines: 1, sorted: null, sorted_at: null }),
        );
      }
      if (url.includes("/api/owner-notes")) {
        return Promise.resolve(
          json({ text: "Old notes.", saved_at: null, lines: 1, sorted: null, sorted_at: null }),
        );
      }
      return Promise.resolve(json({}));
    }),
  );
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const onOpenChange = vi.fn();
  render(
    <QueryClientProvider client={client}>
      <Toaster />
      <EditNotesDialog open onOpenChange={onOpenChange} />
    </QueryClientProvider>,
  );
  return onOpenChange;
}

// The notes editor (P07.5): toasts on save, toast on failure, file button.
describe("EditNotesDialog", () => {
  test("a save toasts", async () => {
    const user = userEvent.setup();
    renderDialog();
    await user.type(await screen.findByLabelText("Your notes"), " More.");
    await user.click(screen.getByRole("button", { name: "Save", exact: true }));
    expect(
      await screen.findByText("Saved. Charie reads your notes in the next learning run."),
    ).toBeTruthy();
  });

  test("a failed save toasts", async () => {
    const user = userEvent.setup();
    renderDialog(500);
    await user.type(await screen.findByLabelText("Your notes"), " More.");
    await user.click(screen.getByRole("button", { name: "Save", exact: true }));
    expect(await screen.findByText("Couldn't save your notes. Try again.")).toBeTruthy();
  });

  test("offers loading a .md or .txt file", async () => {
    renderDialog();
    // jsdom can't pick files; the real file flow is covered in the
    // Sources e2e spec with a real browser.
    const input = await screen.findByLabelText("Load notes from a file");
    expect(input.getAttribute("accept")).toBe(".md,.txt");
    expect(screen.getByRole("button", { name: "Load from a file" })).toBeTruthy();
  });
});
