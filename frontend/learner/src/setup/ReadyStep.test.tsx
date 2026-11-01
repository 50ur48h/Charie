import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, test, vi } from "vitest";
import { ReadyStep } from "./ReadyStep";
import type { Readiness, Usability } from "@charie/shared";

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

const REPORT: Readiness = {
  numbers_checked: 41,
  numbers_total: 45,
  numbers_waiting: 4,
  practice_right: 183,
  practice_total: 200,
  weak_area: "Food waste",
  weak_area_why: "Few documents about it",
};

function renderStep(readiness: Readiness | null, usability: Usability | null = null) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string) =>
      Promise.resolve(
        json(
          url.includes("/api/me")
            ? { logged_in: true, chat_url: "http://localhost:5173" }
            : {},
        ),
      ),
    ),
  );
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/setup?step=5"]}>
        <Routes>
          <Route
            path="/setup"
            element={<ReadyStep readiness={readiness} usability={usability} />}
          />
          <Route path="/learning" element={<p>Learning page</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ReadyStep", () => {
  test("shows the 3 report cards", async () => {
    renderStep(REPORT);
    expect(await screen.findByText("Business numbers checked")).toBeTruthy();
    expect(screen.getByText("41 of 45")).toBeTruthy();
    expect(screen.getByText("183 of 200")).toBeTruthy();
    expect(screen.getByText("Food waste")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Open Charie" })).toBeTruthy();
  });

  test("shows usable numbers and exclusions", async () => {
    const usability: Usability = {
      usable: ["metric.a", "metric.b"],
      excluded: [{ key: "metric.c", title: "Closing stock", reason: "needs a snapshot rule" }],
      usable_defaults: [],
      excluded_defaults: [],
    };
    renderStep(REPORT, usability);
    expect(await screen.findByText("Ready to use")).toBeTruthy();
    expect(screen.getByText(/2 of 3/)).toBeTruthy();
    expect(screen.getByText("Closing stock")).toBeTruthy();
    expect(screen.getByText(/needs a snapshot rule/)).toBeTruthy();
  });

  test("shows Not ready yet without a report", async () => {
    renderStep(null);
    expect(await screen.findByText("Not ready yet")).toBeTruthy();
    expect(screen.getByRole("button", { name: "See learning progress" })).toBeTruthy();
  });
});
