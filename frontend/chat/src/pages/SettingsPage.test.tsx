import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router";
import { Toaster } from "@charie/shared";
import { SettingsPage } from "./SettingsPage";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  document.documentElement.removeAttribute("data-theme");
  localStorage.clear();
});

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const SETTINGS = {
  theme: "sage",
  answer_length: "normal",
  number_format: "short",
  thinking_minutes: 10,
  show_reading: true,
  memory_on: true,
  spend_limit_usd: 150,
  spend_warn_percent: 80,
  time_zone: null,
  strict_mode: false,
  self_test_question_count: 50,
  setup_done: true,
};

const ME = {
  logged_in: true,
  setup_done: true,
  theme: "sage",
  chat_url: "http://localhost:5173",
  learner_url: "http://localhost:5174",
};

const STATUS = {
  questions_waiting: 0,
  knowledge: { version: null, entries: 0, documents: 0, published_at: null },
  data: {
    name: "Bella Forno database",
    kind: "postgres",
    status: "connected",
    data_through: "2025-10-26",
  },
  learning: null,
  spending: { state: "ok", spent_usd: 1, limit_usd: 150, warn_percent: 80, percent_used: 1 },
};

function stubFetch(respond: (url: string, init?: RequestInit) => Response) {
  const calls: { url: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      let body: unknown;
      try {
        body = init?.body ? JSON.parse(String(init.body)) : undefined;
      } catch {
        body = undefined;
      }
      calls.push({ url, body });
      return Promise.resolve(respond(url, init));
    }),
  );
  return { calls };
}

function baseRespond(url: string): Response {
  if (url.includes("/api/settings")) return json(SETTINGS);
  if (url.includes("/api/memories")) return json([]);
  if (url.includes("/api/status")) return json(STATUS);
  if (url.includes("/api/knowledge")) return json({ entries: [], version: 14, status: "published" });
  if (url.includes("/api/me")) return json(ME);
  if (url.includes("/api/logout")) return json({ ok: true });
  return json({});
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  });
  const router = createMemoryRouter(
    [
      { path: "/settings", element: (<><Toaster /><SettingsPage /></>) },
      { path: "/login", element: <p>Login page</p> },
    ],
    { initialEntries: ["/settings"] },
  );
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

describe("SettingsPage", () => {
  test("save_failure shows the API message and keeps the old value", async () => {
    const user = userEvent.setup();
    stubFetch((url, init) => {
      if (url.includes("/api/settings") && (init?.method ?? "GET") === "PATCH") {
        return json({ error: "bad_setting", message: "Answer length must be short, normal or detailed." }, 400);
      }
      return baseRespond(url);
    });
    renderPage();
    await user.click(await screen.findByRole("button", { name: "Detailed" }));
    expect(await screen.findByText("Answer length must be short, normal or detailed.")).toBeTruthy();
    // The control snaps back: Normal stays pressed, Detailed does not.
    expect(screen.getByRole("button", { name: "Normal" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "Detailed" }).getAttribute("aria-pressed")).toBe("false");
  });

  test("theme_persists applies at once and saves", async () => {
    const user = userEvent.setup();
    const { calls } = stubFetch((url, init) =>
      url.includes("/api/settings") && (init?.method ?? "GET") === "PATCH"
        ? json({ ...SETTINGS, ...(JSON.parse(String(init?.body)) as object) })
        : baseRespond(url),
    );
    renderPage();
    await user.click(await screen.findByRole("button", { name: "Seafoam" }));
    expect(document.documentElement.dataset.theme).toBe("seafoam");
    await vi.waitFor(() => {
      expect(calls.some((call) => JSON.stringify(call.body) === JSON.stringify({ theme: "seafoam" }))).toBe(true);
    });
  });

  test("unknown_theme_falls_back shows sage selected", async () => {
    stubFetch(() => json([]));
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string) => {
        if (url.includes("/api/settings")) return Promise.resolve(json({ ...SETTINGS, theme: "banana" }));
        return Promise.resolve(baseRespond(url));
      }),
    );
    renderPage();
    expect(await screen.findByRole("button", { name: "Sage Default" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Sage Default" }).getAttribute("aria-pressed")).toBe("true");
  });

  test("signout_failure_stays on the page with an error", async () => {
    const user = userEvent.setup();
    stubFetch((url) => {
      if (url.includes("/api/logout")) return json({ error: "gone" }, 500);
      return baseRespond(url);
    });
    renderPage();
    await user.click(await screen.findByRole("button", { name: /^Sign out$/ }));
    expect(await screen.findByText("Couldn't sign out. Try again.")).toBeTruthy();
    expect(screen.queryByText("Login page")).toBeNull();
  });
});
