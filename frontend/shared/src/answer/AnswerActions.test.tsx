import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { AnswerActions } from "./AnswerActions";
import { sampleAnswer } from "../mocks/sampleChat";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderActions(failPaths: string[] = []) {
  const calls: { url: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation(async (url: string, init?: RequestInit) => {
      const body = init?.body ? (JSON.parse(init.body as string) as unknown) : undefined;
      calls.push({ url, body });
      if (failPaths.some((path) => url.includes(path))) {
        return Promise.reject(new Error("network down"));
      }
      return Promise.resolve(json({ ok: true }));
    }),
  );
  const written: string[] = [];
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText: (text: string) => (written.push(text), Promise.resolve()) },
  });
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <AnswerActions messageId={2} answer={sampleAnswer(2)} />
    </QueryClientProvider>,
  );
  return { calls, written };
}

describe("AnswerActions", () => {
  test("copy writes readable prose without control labels", async () => {
    const { written } = renderActions();
    fireEvent.click(screen.getByTitle("Copy the answer"));
    await vi.waitFor(() => expect(written).toHaveLength(1));
    expect(written[0]).toContain("October is a good month so far");
    expect(written[0]).not.toContain("This is wrong");
    expect(written[0]).not.toContain("All numbers checked");
    expect(written[0]).not.toContain("You might also ask");
  });

  test("voting toggles and sends once", async () => {
    const { calls } = renderActions();
    const up = screen.getByRole("button", { name: "Good answer" });
    fireEvent.click(up);
    fireEvent.click(up);
    await vi.waitFor(() =>
      expect(calls.filter((call) => call.url.includes("/feedback"))).toHaveLength(1),
    );
    expect(up.getAttribute("aria-pressed")).toBe("true");
    // Clicking again clears the vote.
    fireEvent.click(up);
    await vi.waitFor(() =>
      expect(calls.filter((call) => call.url.includes("/feedback"))).toHaveLength(2),
    );
    expect(up.getAttribute("aria-pressed")).toBe("false");
    expect(calls[1]?.body).toEqual({ vote: null });
  });

  test("a failed vote restores the prior vote", async () => {
    renderActions(["/feedback"]);
    const up = screen.getByRole("button", { name: "Good answer" });
    fireEvent.click(up);
    // The optimistic vote shows until the failure lands, then it restores.
    await vi.waitFor(() => expect(up.getAttribute("aria-pressed")).toBe("false"));
  });

  test("a correction sends once and closes on success", async () => {
    const { calls } = renderActions();
    fireEvent.click(screen.getByRole("button", { name: "This is wrong" }));
    const box = await screen.findByPlaceholderText(/sales should not include/);
    fireEvent.change(box, { target: { value: "Trucks are not delivery." } });
    const send = screen.getByRole("button", { name: "Send correction" });
    fireEvent.click(send);
    fireEvent.click(send);
    await vi.waitFor(() =>
      expect(calls.filter((call) => call.url.includes("/wrong"))).toHaveLength(1),
    );
    expect(calls[0]?.body).toEqual({ correction: "Trucks are not delivery." });
    await vi.waitFor(() =>
      expect(screen.queryByPlaceholderText(/sales should not include/)).toBeNull(),
    );
  });

  test("a failed correction keeps the text", async () => {
    renderActions(["/wrong"]);
    fireEvent.click(screen.getByRole("button", { name: "This is wrong" }));
    const box = await screen.findByPlaceholderText(/sales should not include/);
    fireEvent.change(box, { target: { value: "Keep this text." } });
    fireEvent.click(screen.getByRole("button", { name: "Send correction" }));
    await vi.waitFor(() => expect(screen.getByRole("button", { name: "Send correction" })).toBeTruthy());
    // Still open with the text preserved.
    expect(
      (screen.getByPlaceholderText(/sales should not include/) as HTMLTextAreaElement).value,
    ).toBe("Keep this text.");
  });
});
