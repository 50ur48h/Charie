import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, test, vi } from "vitest";
import { DatabaseCard } from "./DatabaseCard";
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

const SOURCE: DatabaseSource = {
  kind: "postgres",
  name: "Bella Forno database",
  host: "bellaforno-db.postgres.database.azure.com",
  port: 5432,
  database: "bella_forno",
  username: "charie_readonly",
  status: "connected",
  read_only_ok: true,
  data_through: "2026-10-26",
  checked_at: "2025-10-27T19:30:00+05:30",
  details: { tables: 57, rows: 2400000 },
};

function renderCard(source: DatabaseSource | null) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes("/api/sources/database") && (init?.method ?? "GET") === "GET") {
        return Promise.resolve(json(source));
      }
      return Promise.resolve(json({}));
    }),
  );
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/sources"]}>
        <Routes>
          <Route path="/sources" element={<DatabaseCard />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("DatabaseCard", () => {
  test("shows the connection like the design", async () => {
    renderCard(SOURCE);
    expect(await screen.findByText("Bella Forno database")).toBeTruthy();
    expect(screen.getByText("Connected")).toBeTruthy();
    expect(
      screen.getByText(/Postgres · bellaforno-db · read-only login · checked/),
    ).toBeTruthy();
    expect(screen.getByText("57")).toBeTruthy();
    expect(screen.getByText("2.4M")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Edit" })).toBeTruthy();
  });

  test("shows Connect when there's no database", async () => {
    renderCard(null);
    expect(await screen.findByText("No database connected")).toBeTruthy();
    expect(screen.getByText("Connect one so Charie can learn your data.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Connect" }));
    expect(await screen.findByText("Database connection")).toBeTruthy();
  });
});
