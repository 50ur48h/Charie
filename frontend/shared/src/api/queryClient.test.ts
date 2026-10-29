import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render } from "@testing-library/react";
import React, { useEffect } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { apiFetch } from "./client";
import { createQueryClient } from "./queryClient";
import { loggedOutMe } from "./hooks";
import { useUpdateSettings } from "./settings";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

function unauthorized(): Response {
  return new Response(JSON.stringify({ error: "login_needed", message: "Please sign in." }), {
    status: 401,
    headers: { "Content-Type": "application/json" },
  });
}

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

describe("expired mutations", () => {
  test("a 401 settings save clears cached data and marks you logged out", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(unauthorized()));
    const client = createQueryClient();
    client.setQueryData(["me"], { ...loggedOutMe(), logged_in: true });
    client.setQueryData(["settings"], { theme: "sage" });
    let settled = false;
    function Probe() {
      const update = useUpdateSettings();
      useEffect(() => {
        update.mutate(
          { theme: "mist" },
          { onError: () => undefined, onSettled: () => (settled = true) },
        );
        // eslint-disable-next-line react-hooks/exhaustive-deps
      }, []);
      return null;
    }
    render(React.createElement(QueryClientProvider, { client }, React.createElement(Probe)));
    await vi.waitFor(() => expect(settled).toBe(true));
    expect(client.getQueryData(["me"])).toMatchObject({ logged_in: false });
    expect(client.getQueryData(["settings"])).toBeUndefined();
  });
});
