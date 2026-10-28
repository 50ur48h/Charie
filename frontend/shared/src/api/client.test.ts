import { afterEach, describe, expect, test, vi } from "vitest";
import { ApiError, apiFetch } from "./client";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
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
