import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, test, vi } from "vitest";
import { RefreshBanner } from "./RefreshBanner";
import type { LearningRun, RefreshStatus } from "@charie/shared";

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

function run(status: LearningRun["status"]): LearningRun {
  return {
    id: 1,
    kind: "refresh",
    status,
    paused_by: null,
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

const EMPTY: RefreshStatus = { documents: [], removed: [], notes_changed: false };

function renderBanner(status: RefreshStatus, runs: LearningRun[]) {
  const posted: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes("/api/learning/refresh-status")) return Promise.resolve(json(status));
      if (url.includes("/api/learning/refresh")) {
        if (init?.method === "POST") posted.push(url);
        return Promise.resolve(json({ ok: true }));
      }
      if (url.includes("/api/learning")) return Promise.resolve(json({ runs }));
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
  return { posted };
}

describe("RefreshBanner", () => {
  test("shows new documents", async () => {
    renderBanner({ documents: [1, 2, 3], removed: [], notes_changed: false }, []);
    expect(await screen.findByText("3 new documents since the last learning")).toBeTruthy();
  });

  test("hides when nothing is pending", async () => {
    renderBanner(EMPTY, []);
    await waitFor(() =>
      expect(
        vi
          .mocked(fetch)
          .mock.calls.some(([url]) => String(url).includes("refresh-status")),
      ).toBe(true),
    );
    expect(screen.queryByText(/since the last learning/)).toBeNull();
  });

  test("starts a refresh when nothing is running", async () => {
    const { posted } = renderBanner({ documents: [1], removed: [], notes_changed: false }, []);
    fireEvent.click(await screen.findByRole("button", { name: "Refresh knowledge base" }));
    expect(await screen.findByText("Learning page")).toBeTruthy();
    expect(posted).toEqual(["/api/learning/refresh"]);
  });

  test("only opens Learning while a run is going", async () => {
    const { posted } = renderBanner({ documents: [1], removed: [], notes_changed: false }, [run("running")]);
    fireEvent.click(await screen.findByRole("button", { name: "Refresh knowledge base" }));
    expect(await screen.findByText("Learning page")).toBeTruthy();
    expect(posted).toEqual([]);
  });

  test("says notes changed", async () => {
    renderBanner({ documents: [], removed: [], notes_changed: true }, [run("done")]);
    expect(await screen.findByText("Your notes changed since the last learning")).toBeTruthy();
  });

  test("says documents and notes", async () => {
    renderBanner({ documents: [1, 2], removed: [], notes_changed: true }, []);
    expect(
      await screen.findByText("2 new documents and changed notes since the last learning"),
    ).toBeTruthy();
  });

  test("shows a removed document", async () => {
    renderBanner({ documents: [], removed: [7], notes_changed: false }, [run("done")]);
    expect(await screen.findByText("1 removed document since the last learning")).toBeTruthy();
  });

  test("keeps pending changes after a failed run", async () => {
    const { posted } = renderBanner({ documents: [1], removed: [], notes_changed: false }, [run("failed")]);
    expect(await screen.findByText("1 new document since the last learning")).toBeTruthy();
    fireEvent.click(await screen.findByRole("button", { name: "Refresh knowledge base" }));
    expect(await screen.findByText("Learning page")).toBeTruthy();
    expect(posted).toEqual(["/api/learning/refresh"]);
  });
});
