import { afterEach, describe, expect, test, vi } from "vitest";
import { apiFetch } from "./client";
import { createQueryClient } from "./queryClient";

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("createQueryClient", () => {
  test("a 401 from any query clears cached data and marks you logged out", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ error: "nope", message: "Gone." }), {
          status: 401,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    const client = createQueryClient();
    client.setQueryData(["settings"], { theme: "mist" });
    await client
      .fetchQuery({ queryKey: ["thing"], queryFn: () => apiFetch("/api/thing") })
      .catch(() => undefined);
    expect(client.getQueryData(["me"])).toMatchObject({ logged_in: false });
    expect(client.getQueryData(["settings"])).toBeUndefined();
  });
});
