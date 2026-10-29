import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createQueryClient } from "../api/queryClient";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { MemoryRouter } from "react-router";
import { LoginPage } from "./LoginPage";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function loggedOut() {
  return { logged_in: false, setup_done: false, theme: "sage", chat_url: "http://localhost:5173", learner_url: "http://localhost:5174" };
}

function renderLogin(app: "chat" | "learner", me: unknown = loggedOut()) {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(me), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  });
  function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={client}>
        <MemoryRouter>{children}</MemoryRouter>
      </QueryClientProvider>
    );
  }
  render(<LoginPage app={app} />, { wrapper: Wrapper });
  return { fetchMock };
}

describe("LoginPage", () => {
  test("a wrong password shows the API message", async () => {
    const fetchMock = vi.fn(async (url: unknown) => {
      if (String(url).endsWith("/api/login")) {
        return new Response(
          JSON.stringify({ error: "wrong_password", message: "That password didn't work. Try again." }),
          { status: 401, headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response(JSON.stringify(loggedOut()), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    const client = createQueryClient();
    function Wrapper({ children }: { children: React.ReactNode }) {
      return (
        <QueryClientProvider client={client}>
          <MemoryRouter>{children}</MemoryRouter>
        </QueryClientProvider>
      );
    }
    render(<LoginPage app="chat" />, { wrapper: Wrapper });
    await screen.findByRole("heading", { name: "Welcome back" });
    fireEvent.change(screen.getByPlaceholderText("Enter the password"), {
      target: { value: "nope" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect((await screen.findByRole("alert")).textContent).toContain(
      "That password didn't work. Try again.",
    );
  });

  test("shows the chat words", async () => {
    renderLogin("chat");
    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeTruthy();
    expect(screen.getByText("Sign in to Charie.")).toBeTruthy();
    expect(
      screen.getByText("Ask anything about your business. Get answers you can trust."),
    ).toBeTruthy();
    expect(screen.getByText("Checks every number before showing it")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Open Charie Learner" })).toBeTruthy();
  });

  test("shows the learner words and the Learner tag", async () => {
    renderLogin("learner");
    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeTruthy();
    expect(screen.getByText("Sign in to Charie Learner.")).toBeTruthy();
    expect(screen.getByText("Teach Charie your business.")).toBeTruthy();
    expect(screen.getByText("Connect your database, read-only")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Charie Learner" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Sign in to Charie" })).toBeTruthy();
  });

  test("an empty password shows a message without calling the API", async () => {
    const { fetchMock } = renderLogin("chat");
    await screen.findByRole("heading", { name: "Welcome back" });
    const loginCalls = fetchMock.mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Please enter the password.");
    expect(fetchMock.mock.calls.length).toBe(loginCalls);
    expect(document.activeElement?.getAttribute("id")).toBe("password");
  });

  test("the eye button shows and hides the password", async () => {
    renderLogin("chat");
    const box = (await screen.findByPlaceholderText("Enter the password")) as HTMLInputElement;
    expect(box.type).toBe("password");
    fireEvent.click(screen.getByRole("button", { name: "Show password" }));
    expect(box.type).toBe("text");
    fireEvent.click(screen.getByRole("button", { name: "Hide password" }));
    expect(box.type).toBe("password");
  });
});
