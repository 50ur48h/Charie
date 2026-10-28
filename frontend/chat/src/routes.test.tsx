import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router";
import { routes } from "./routes";

const ME = '{"logged_in": true, "setup_done": true, "theme": "sage"}';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function renderAt(path: string) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string) =>
      Promise.resolve(
        new Response(url.includes("/api/me") ? ME : "[]", {
          headers: { "Content-Type": "application/json" },
        }),
      ),
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

describe("chat routes", () => {
  test("shows the Usage page at /usage", async () => {
    renderAt("/usage");
    expect(await screen.findByRole("heading", { name: "Usage" })).toBeTruthy();
    expect(
      screen.getByText("What Charie's AI has cost this month.", { exact: false }),
    ).toBeTruthy();
  });

  test("shows Page not found for an unknown address", async () => {
    renderAt("/nope");
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Go to the start" })).toBeTruthy();
  });
});
