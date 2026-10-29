import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import React from "react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { ApiError, apiFetch } from "./client";
import { useMe } from "./hooks";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("apiFetch", () => {
  test("sends and reads JSON", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(apiFetch("/api/me")).resolves.toEqual({ ok: true });
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.headers).toMatchObject({ Accept: "application/json" });
    expect(init.body).toBeUndefined();
  });

  test("sends {} as the body when a change has none", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, {}));
    vi.stubGlobal("fetch", fetchMock);
    await apiFetch("/api/x", { method: "POST" });
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe("POST");
    expect(init.headers).toMatchObject({
      Accept: "application/json",
      "Content-Type": "application/json",
    });
    expect(init.body).toBe("{}");
  });

  test("throws the server's plain-English message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse(404, { error: "nope", message: "Gone." })),
    );
    const error = await apiFetch("/api/x").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(404);
    expect((error as ApiError).code).toBe("nope");
    expect((error as ApiError).message).toBe("Gone.");
  });

  test("uses a plain-English message when the server gives none", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("<html>boom</html>", { status: 500 })),
    );
    const error = await apiFetch("/api/x").catch((e: unknown) => e);
    expect((error as ApiError).status).toBe(500);
    expect((error as ApiError).code).toBe("http_500");
    expect((error as ApiError).message).toContain("Something went wrong");
  });

  test("turns a failed connection into Can't reach Charie", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fetch failed")));
    const error = await apiFetch("/api/x").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(0);
    expect((error as ApiError).code).toBe("network");
    expect((error as ApiError).message).toContain("Can't reach Charie");
  });

  test("resolves undefined on 204 with no body", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    await expect(apiFetch("/api/x", { method: "POST" })).resolves.toBeUndefined();
  });

  test("names too many tries in plain English", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("slow", { status: 429 })));
    const error = await apiFetch("/api/x").catch((e: unknown) => e);
    expect((error as ApiError).status).toBe(429);
    expect((error as ApiError).message).toContain("Too many tries");
  });
});

describe("useMe", () => {
  test("a 401 from /api/me means logged out", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ error: "login_needed", message: "Please sign in." }), {
          status: 401,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
    });
    function Probe() {
      const me = useMe();
      if (me.isPending) return React.createElement("p", null, "loading");
      if (me.isError) return React.createElement("p", null, "broke");
      return React.createElement("p", null, me.data.logged_in ? "in" : "out");
    }
    render(React.createElement(QueryClientProvider, { client }, React.createElement(Probe)));
    expect(await screen.findByText("out")).toBeTruthy();
  });
});
