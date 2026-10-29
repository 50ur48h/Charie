import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { useLearnerBadges } from "./useLearnerBadges";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function json(data: unknown): Response {
  return new Response(JSON.stringify(data), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function stubFetch(documents: unknown[], runs: unknown[], entries: unknown[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string) => {
      if (url.includes("/api/documents")) return Promise.resolve(json({ documents }));
      if (url.includes("/api/learning")) return Promise.resolve(json({ runs }));
      if (url.includes("/api/knowledge")) return Promise.resolve(json({ entries, version: 14 }));
      return Promise.resolve(json({}));
    }),
  );
}

function renderBadges() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  });
  return renderHook(() => useLearnerBadges(), {
    wrapper: ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    ),
  });
}

const DOC = (status: string) => ({ id: 1, file_name: "a.pdf", status, uploaded_at: "2025-10-27T21:00:00+05:30" });

describe("useLearnerBadges", () => {
  test("counts new and reading documents", async () => {
    stubFetch(
      [
        { ...DOC("new"), id: 1 },
        { ...DOC("reading"), id: 2 },
        { ...DOC("learned"), id: 3 },
      ],
      [],
      [],
    );
    const { result } = renderBadges();
    await waitFor(() => expect(result.current.newDocuments).toBe(2));
  });

  test("shows the live dot only while running", async () => {
    stubFetch([], [{ id: 4, status: "running", started_at: "2025-10-27T21:12:00+05:30" }], []);
    const { result } = renderBadges();
    await waitFor(() => expect(result.current.learningNow).toBe(true));
  });

  test("hides the dot for a done run", async () => {
    stubFetch(
      [{ ...DOC("new"), id: 1 }],
      [{ id: 3, status: "done", started_at: "2025-10-26T02:00:00+05:30" }],
      [],
    );
    const { result } = renderBadges();
    // The new document proves the fetches landed; the done run shows no dot.
    await waitFor(() => expect(result.current.newDocuments).toBe(1));
    expect(result.current.learningNow).toBe(false);
  });

  test("counts guessed and conflicting entries", async () => {
    stubFetch(
      [],
      [],
      [
        { key: "a", confidence: "guess" },
        { key: "b", confidence: "conflict" },
        { key: "c", confidence: "owner" },
      ],
    );
    const { result } = renderBadges();
    await waitFor(() => expect(result.current.needsReview).toBe(2));
  });

  test("reports zero when everything is settled", async () => {
    stubFetch([{ ...DOC("learned"), id: 1 }], [], [{ key: "c", confidence: "owner" }]);
    const { result } = renderBadges();
    await waitFor(() => expect(result.current.newDocuments).toBe(0));
    expect(result.current.learningNow).toBe(false);
    expect(result.current.needsReview).toBe(0);
  });
});
