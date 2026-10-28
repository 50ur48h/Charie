import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router";
import { routes } from "./routes";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function renderAt(path: string) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response('{"logged_in": true, "setup_done": true, "theme": "sage"}', {
        headers: { "Content-Type": "application/json" },
      }),
    ),
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
});
