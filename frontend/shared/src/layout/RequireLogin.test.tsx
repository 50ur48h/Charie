import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router";
import { RequireLogin } from "./RequireLogin";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
  delete document.documentElement.dataset.theme;
});

function renderGuarded(me: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify(me), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    ),
  );
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  });
  function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  }
  const router = createMemoryRouter(
    [
      {
        path: "/",
        element: (
          <RequireLogin>
            <p>the page</p>
          </RequireLogin>
        ),
      },
      { path: "/login", element: <p>the login page</p> },
    ],
    { initialEntries: ["/"] },
  );
  render(<RouterProvider router={router} />, { wrapper: Wrapper });
}

describe("RequireLogin", () => {
  test("sends you to /login when you're logged out", async () => {
    renderGuarded({ logged_in: false, setup_done: false, theme: "sage", chat_url: "http://localhost:5173", learner_url: "http://localhost:5174" });
    expect(await screen.findByText("the login page")).toBeTruthy();
    expect(screen.queryByText("the page")).toBeNull();
  });

  test("shows the page when you're logged in", async () => {
    renderGuarded({ logged_in: true, setup_done: true, theme: "sage", chat_url: "http://localhost:5173", learner_url: "http://localhost:5174" });
    expect(await screen.findByText("the page")).toBeTruthy();
    expect(screen.queryByText("the login page")).toBeNull();
  });

  test("switches to the theme from /api/me", async () => {
    document.documentElement.dataset.theme = "sage";
    renderGuarded({ logged_in: true, setup_done: true, theme: "lavender", chat_url: "http://localhost:5173", learner_url: "http://localhost:5174" });
    await screen.findByText("the page");
    expect(document.documentElement.dataset.theme).toBe("lavender");
  });
});
