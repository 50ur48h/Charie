import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, test, vi } from "vitest";
import { SetupPage } from "./SetupPage";

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

function renderSetup(setupDone: boolean) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string) =>
      Promise.resolve(
        json(
          url.includes("/api/setup")
            ? { setup_done: setupDone, step: 5, readiness: null }
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
          <Route path="/setup" element={<SetupPage />} />
          <Route path="/sources" element={<p>Sources page</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("SetupPage", () => {
  test("redirects to Sources when setup is done", async () => {
    renderSetup(true);
    expect(await screen.findByText("Sources page")).toBeTruthy();
  });

  test("shows the guide while setup is open", async () => {
    renderSetup(false);
    expect(await screen.findByText("Set up Charie")).toBeTruthy();
  });
});
