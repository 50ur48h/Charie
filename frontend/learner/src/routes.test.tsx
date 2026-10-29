import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router";
import { routes } from "./routes";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

// Endpoint-aware stub: the frame fires several queries (me, documents,
// runs, knowledge) and the pages fire their own.
function renderAt(path: string, setupDone = false) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string) => {
      const body = (data: unknown): Promise<Response> =>
        Promise.resolve(
          new Response(JSON.stringify(data), {
            headers: { "Content-Type": "application/json" },
          }),
        );
      if (url.includes("/api/me")) {
        return body({
          logged_in: true,
          setup_done: setupDone,
          theme: "sage",
          chat_url: "http://localhost:5173",
          learner_url: "http://localhost:5174",
        });
      }
      if (url.includes("/api/setup")) return body({ setup_done: setupDone, step: 1, readiness: null });
      if (url.includes("/api/sources/database")) return body({ source: null });
      if (url.includes("/api/documents")) return body({ documents: [] });
      if (url.includes("/api/learning")) return body({ runs: [] });
      if (url.includes("/api/knowledge")) return body({ entries: [], version: null });
      if (url.includes("/api/questions")) return body({ questions: [] });
      return body({});
    }),
  );
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={createMemoryRouter(routes, { initialEntries: [path] })} />
    </QueryClientProvider>,
  );
}

describe("learner routes", () => {
  test("shows the setup guide at /setup", async () => {
    renderAt("/setup");
    expect(await screen.findByRole("heading", { name: "Set up Charie" })).toBeTruthy();
  });

  test("sends / to /setup", async () => {
    renderAt("/");
    expect(await screen.findByRole("heading", { name: "Set up Charie" })).toBeTruthy();
  });

  test("sends / to /sources once setup is done", async () => {
    renderAt("/", true);
    expect(await screen.findByRole("heading", { name: "Sources" })).toBeTruthy();
  });
});
