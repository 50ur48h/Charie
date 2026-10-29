import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import type { KbVersion } from "@charie/shared";
import { DraftBanner } from "./DraftBanner";

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

function version(number: number, status: KbVersion["status"]): KbVersion {
  return {
    id: number,
    number,
    status,
    made_by: status === "draft" ? "refresh" : "nightly",
    created_at: "2026-10-27T21:12:00+05:30",
    published_at: status === "draft" ? null : "2026-10-20T02:06:00+05:30",
    summary: {
      added: 3,
      changed: 2,
      removed: 1,
      note: "3 new facts from new documents · 2 updated meanings · 1 removed",
    },
  };
}

function renderBanner(versions: KbVersion[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string) => {
      if (url.includes("/api/versions")) {
        const draft = versions.find((version) => version.status === "draft");
        const live = versions.find((version) => version.status === "published");
        return Promise.resolve(
          json({ versions, live: live?.number ?? null, draft: draft?.number ?? null }),
        );
      }
      return Promise.resolve(json({}));
    }),
  );
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <DraftBanner onReview={vi.fn()} onPublish={vi.fn()} />
    </QueryClientProvider>,
  );
}

describe("DraftBanner", () => {
  test("shows draft 15 with 6 changes", async () => {
    renderBanner([version(15, "draft"), version(14, "published")]);
    await waitFor(() => {
      expect(screen.getByText("Draft version 15 has 6 changes")).not.toBeNull();
    });
    expect(
      screen.getByText(/3 new facts from new documents.*Version 14 stays live until you publish\./),
    ).not.toBeNull();
    expect(screen.getByRole("button", { name: "Review changes" })).not.toBeNull();
    expect(screen.getByRole("button", { name: "Publish version 15" })).not.toBeNull();
  });

  test("hides with no draft", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(() => Promise.resolve(json({ versions: [], live: 14, draft: null }))),
    );
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    const { container } = render(
      <QueryClientProvider client={client}>
        <DraftBanner onReview={vi.fn()} onPublish={vi.fn()} />
      </QueryClientProvider>,
    );
    await waitFor(() => {
      expect(container.firstChild).toBeNull();
    });
  });
});