import { afterEach, describe, expect, it, vi } from "vitest";

import { mintDevToken } from "./dev-tokens";

function stubTokenResponse() {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ access_token: "token-1" }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("mintDevToken", () => {
  it("resolves a relative API address against the page (single image)", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "/api");
    const fetchMock = stubTokenResponse();

    await expect(mintDevToken("ana")).resolves.toEqual({ subject: "ana", token: "token-1" });

    const url = fetchMock.mock.calls[0]?.[0] as URL;
    expect(url.origin).toBe(window.location.origin);
    expect(url.pathname).toBe("/api/dev/token");
    expect(url.searchParams.get("sub")).toBe("ana");
  });

  it("keeps an absolute API address as it is", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://api.test");
    const fetchMock = stubTokenResponse();

    await mintDevToken("ana");

    const url = fetchMock.mock.calls[0]?.[0] as URL;
    expect(url.origin).toBe("http://api.test");
    expect(url.pathname).toBe("/dev/token");
  });
});
