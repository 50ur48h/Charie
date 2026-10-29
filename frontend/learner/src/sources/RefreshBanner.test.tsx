import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, test, vi } from "vitest";
import { RefreshBanner } from "./RefreshBanner";
import type { LearnerDocument, LearningRun } from "@charie/shared";

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

function doc(id: number, status: LearnerDocument["status"]): LearnerDocument {
  return {
    id,
    file_name: `doc-${id}.pdf`,
    file_type: "pdf",
    size_bytes: 1024,
    pages: 2,
    unreadable_pages: 0,
    fact_count: 0,
    status,
    progress: null,
    error: null,
    uploaded_at: "2025-10-27T21:00:00+05:30",
    learned_at: null,
  };
}

function run(status: LearningRun["status"]): LearningRun {
  return {
    id: 1,
    kind: "refresh",
    status,
    reason: "3 new documents",
    step: 8,
    percent: 62,
    minutes_left: 25,
    progress: [],
    cost_usd: 3.8,
    summary: null,
    version_number: 15,
    new_version: true,
    started_at: "2025-10-27T21:12:00+05:30",
    finished_at: null,
  };
}

function renderBanner(documents: LearnerDocument[], runs: LearningRun[], savedAt: string | null = null) {
  const posted: string[] = [];
  const fetched: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string) => {
      fetched.push(url);
      if (url.includes("/api/learning/refresh")) {
        posted.push(url);
        return Promise.resolve(json({ ok: true }));
      }
      if (url.includes("/api/learning")) return Promise.resolve(json({ runs }));
      if (url.includes("/api/documents")) return Promise.resolve(json({ documents })); if (url.includes("owner-notes"))
        return Promise.resolve(json({ text: "My rule.", saved_at: savedAt, sorted: null, sorted_at: null }));
      return Promise.resolve(json({}));
    }),
  );
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/sources"]}>
        <Routes>
          <Route path="/sources" element={<RefreshBanner />} />
          <Route path="/learning" element={<p>Learning page</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { posted, fetched };
}

describe("RefreshBanner", () => {
  test("shows 3 new documents", async () => {
    renderBanner([doc(1, "new"), doc(2, "new"), doc(3, "reading"), doc(4, "learned")], []);
    expect(await screen.findByText("3 new documents since the last learning")).toBeTruthy();
  });

  test("hides when nothing is new", async () => {
    const { fetched } = renderBanner([doc(1, "learned")], []);
    await waitFor(() =>
      expect(fetched.some((url) => url.includes("/api/documents"))).toBe(true),
    );
    expect(screen.queryByText(/since the last learning/)).toBeNull();
  });

  test("starts a refresh when nothing is running", async () => {
    const { posted } = renderBanner([doc(1, "new")], []);
    fireEvent.click(await screen.findByRole("button", { name: "Refresh knowledge base" }));
    expect(await screen.findByText("Learning page")).toBeTruthy();
    expect(posted).toEqual(["/api/learning/refresh"]);
  });

  test("only opens Learning while a run is going", async () => {
    const { posted } = renderBanner([doc(1, "new")], [run("running")]);
    fireEvent.click(await screen.findByRole("button", { name: "Refresh knowledge base" }));
    expect(await screen.findByText("Learning page")).toBeTruthy();
    expect(posted).toEqual([]);
  });

  test("says notes changed", async () => {
    renderBanner([doc(1, "learned")], [run("done")], "2026-10-27T21:00:00+05:30");
    expect(await screen.findByText("Your notes changed since the last learning")).toBeTruthy();
  });

  test("says documents and notes", async () => {
    renderBanner([doc(1, "new"), doc(2, "new")], [], "2026-10-27T21:00:00+05:30");
    expect(
      await screen.findByText("2 new documents and changed notes since the last learning"),
    ).toBeTruthy();
  });

  test("stays hidden when notes predate the run", async () => {
    const { fetched } = renderBanner([doc(1, "learned")], [run("done")], "2025-10-26T21:00:00+05:30");
    await waitFor(() => expect(fetched.some((url) => url.includes("owner-notes"))).toBe(true));
    expect(screen.queryByText(/since the last learning/)).toBeNull();
  });
});
