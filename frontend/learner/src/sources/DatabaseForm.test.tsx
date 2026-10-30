import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { DatabaseForm } from "./DatabaseForm";
import type { DatabaseSource } from "@charie/shared";

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

const SAVED: DatabaseSource = {
  kind: "postgres",
  name: "Bella Forno database",
  host: "db.internal",
  port: 5432,
  database: "bella_forno",
  username: "charie_readonly",
  status: "connected",
  read_only_ok: true,
  data_through: "2026-10-26",
  checked_at: "2025-10-27T19:30:00+05:30",
  details: { tables: 57, rows: 2400000 },
};

const TEST_OK = {
  read_only_ok: true,
  data_through: "2026-10-26",
  details: { tables: 57, rows: 2400000 },
};

function stubFetch(respond: (url: string, init?: RequestInit) => Response) {
  const puts: unknown[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes("/api/sources/database/test")) return Promise.resolve(respond(url, init));
      if (url.includes("/api/sources/database") && (init?.method ?? "GET") === "PUT") {
        try {
          puts.push(JSON.parse(String(init?.body)));
        } catch {
          puts.push(undefined);
        }
        return Promise.resolve(respond(url, init));
      }
      return Promise.resolve(json({}));
    }),
  );
  return { puts };
}

function renderForm(initial: DatabaseSource | null, onSubmitted: () => void = () => {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <DatabaseForm initial={initial} submitLabel="Continue" onSubmitted={onSubmitted} />
    </QueryClientProvider>,
  );
}

describe("DatabaseForm", () => {
  test("a changed host passes the test, then Continue saves", async () => {
    const onSubmitted = vi.fn();
    stubFetch(() => json(TEST_OK));
    renderForm(SAVED, onSubmitted);
    fireEvent.change(screen.getByLabelText("Server address"), { target: { value: "db2.internal" } });
    fireEvent.click(screen.getByRole("button", { name: /Test connection/ }));
    expect(await screen.findByText("Connection works")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    await waitFor(() => expect(onSubmitted).toHaveBeenCalled());
  });

  test("an empty port disables Test and Continue", () => {
    stubFetch(() => json(TEST_OK));
    renderForm(null);
    fireEvent.change(screen.getByLabelText("Server address"), { target: { value: "db.internal" } });
    fireEvent.change(screen.getByLabelText("Port"), { target: { value: "" } });
    fireEvent.change(screen.getByLabelText("Database name"), { target: { value: "bella_forno" } });
    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "charie_readonly" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "secret" } });
    expect(
      (screen.getByRole("button", { name: /Test connection/ }) as HTMLButtonElement).disabled,
    ).toBe(true);
    expect((screen.getByRole("button", { name: "Continue" }) as HTMLButtonElement).disabled).toBe(
      true,
    );
  });

  test("a wrong password shows the API message", async () => {
    stubFetch(() =>
      json({ error: "login_failed", message: "The username or password is wrong." }, 400),
    );
    renderForm(SAVED);
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "wrong" } });
    fireEvent.click(screen.getByRole("button", { name: /Test connection/ }));
    expect(await screen.findByText("The username or password is wrong.")).toBeTruthy();
  });

  test("a saved source with no changes goes straight on", async () => {
    const onSubmitted = vi.fn();
    const { puts } = stubFetch(() => json(SAVED));
    renderForm(SAVED, onSubmitted);
    fireEvent.click(await screen.findByRole("button", { name: "Continue" }));
    expect(onSubmitted).toHaveBeenCalled();
    expect(puts).toEqual([]);
  });
});
