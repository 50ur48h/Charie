import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, test, vi } from "vitest";
import { LearnStep } from "./LearnStep";
import { shortDate } from "../lib/when";

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

function renderStep(runs: unknown[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes("/api/learning") && (init?.method ?? "GET") === "GET") {
        return Promise.resolve(json({ runs }));
      }
      if (url.includes("/api/learning/start")) {
        return Promise.resolve(json({ ok: true }));
      }
      if (url.includes("/api/sources/database")) {
        return Promise.resolve(
          json({ details: { tables: 57, rows: 2400000 } }),
        );
      }
      if (url.includes("/api/documents")) {
        return Promise.resolve(json({ documents: [] }));
      }
      if (url.includes("/api/owner-notes")) {
        return Promise.resolve(json({ text: "", saved_at: null, sorted: null, sorted_at: null }));
      }
      return Promise.resolve(json({}));
    }),
  );
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/setup?step=3"]}>
        <Routes>
          <Route path="/setup" element={<LearnStep onBack={() => {}} onNext={() => {}} />} />
          <Route path="/learning" element={<p>Learning page</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("LearnStep", () => {
  test("shows Ready to learn without a first run", async () => {
    renderStep([]);
    expect(await screen.findByText("Ready to learn")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Start learning" })).toBeTruthy();
  });

  test("Start learning opens the Learning page", async () => {
    renderStep([]);
    fireEvent.click(await screen.findByRole("button", { name: "Start learning" }));
    expect(await screen.findByText("Learning page")).toBeTruthy();
  });

  test("a done run shows when it finished", async () => {
    renderStep([
      {
        id: 1,
        kind: "first",
        status: "done",
        step: 12,
        percent: 100,
        started_at: "2025-10-03T10:05:00+05:30",
        finished_at: "2025-10-03T11:53:00+05:30",
      },
    ]);
    expect(await screen.findByText("Charie has learned your business")).toBeTruthy();
    const finished = `Finished ${shortDate("2025-10-03T11:53:00+05:30")}`;
    expect(
      screen.getByText((_, element) => element?.textContent === finished),
    ).toBeTruthy();
  });
});
