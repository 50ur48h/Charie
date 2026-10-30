import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, test, vi } from "vitest";
import { DatabaseStep } from "./DatabaseStep";

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

// The real GET /api/sources/database returns a bare DatabaseSource, or a
// bare null when nothing is saved (the plan's contract). The step must not
// crash on the bare null.
function renderStep(body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string) => {
      if (url.includes("/api/sources/database")) return Promise.resolve(json(body));
      return Promise.resolve(json({}));
    }),
  );
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/setup"]}>
        <Routes>
          <Route path="/setup" element={<DatabaseStep onDone={() => {}} />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("DatabaseStep", () => {
  test("shows the empty form when no database is saved", async () => {
    renderStep(null);
    expect(
      await screen.findByRole("heading", { name: "Connect your database" }),
    ).toBeTruthy();
    expect(await screen.findByLabelText("Server address", {}, { timeout: 5000 })).toBeTruthy();
    expect(await screen.findByRole("button", { name: "Continue" })).toBeTruthy();
  });
});
