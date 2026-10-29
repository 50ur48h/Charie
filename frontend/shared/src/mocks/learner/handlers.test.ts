import { setupServer } from "msw/node";
import { afterEach, beforeAll, describe, expect, test } from "vitest";
import { handlers } from "../handlers";
import { resetLearnerMock } from "./state";

const APP = "https://charie.invalid";

const server = setupServer(...handlers);

beforeAll(() => server.listen({ onUnhandledFrame: "error" }));
afterEach(() => {
  server.resetHandlers();
  localStorage.clear();
  sessionStorage.clear();
  resetLearnerMock("design");
});

async function signIn(): Promise<void> {
  const login = await fetch(`${APP}/api/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password: "bella-forno" }),
  });
  expect(login.status).toBe(200);
}

async function putDatabase(body: unknown): Promise<Response> {
  return fetch(`${APP}/api/sources/database`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

const GOOD = {
  kind: "postgres",
  host: "db.internal",
  port: 5432,
  database: "bella_forno",
  username: "charie_readonly",
  password: "right-password",
};

describe("learner setup mocks", () => {
  test("refuses a login that can change data", async () => {
    await signIn();
    const response = await fetch(`${APP}/api/sources/database/test`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...GOOD, username: "admin" }),
    });
    expect(response.status).toBe(400);
    await expect(response.json()).resolves.toMatchObject({ error: "not_read_only" });
  });

  test("a wrong server or password fails plainly", async () => {
    await signIn();
    const unreachable = await fetch(`${APP}/api/sources/database/test`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...GOOD, host: "wrong-host" }),
    });
    expect(unreachable.status).toBe(400);
    await expect(unreachable.json()).resolves.toMatchObject({ error: "cant_connect" });
    const badPassword = await fetch(`${APP}/api/sources/database/test`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...GOOD, password: "wrong" }),
    });
    expect(badPassword.status).toBe(400);
    await expect(badPassword.json()).resolves.toMatchObject({ error: "login_failed" });
  });

  test("saves the source without the password", async () => {
    await signIn();
    const response = await putDatabase(GOOD);
    expect(response.status).toBe(200);
    const { source } = (await response.json()) as { source: Record<string, unknown> };
    expect(source).toMatchObject({
      name: "Bella Forno database",
      host: "db.internal",
      status: "connected",
      read_only_ok: true,
      data_through: "2026-10-26",
      details: { tables: 57, rows: 2400000 },
    });
    expect("password" in source).toBe(false);
    expect(typeof source.checked_at).toBe("string");
    const fetched = (await (await fetch(`${APP}/api/sources/database`)).json()) as {
      source: Record<string, unknown>;
    };
    expect("password" in fetched.source).toBe(false);
  });

  test("an empty password keeps the saved one", async () => {
    await signIn();
    await putDatabase(GOOD);
    const again = await putDatabase({ ...GOOD, host: "db2.internal", password: "" });
    expect(again.status).toBe(200);
    const { source } = (await again.json()) as { source: { host: string } };
    expect(source.host).toBe("db2.internal");
  });

  test("setup state walks the steps in the design world", async () => {
    await signIn();
    const response = await fetch(`${APP}/api/setup`);
    await expect(response.json()).resolves.toMatchObject({
      setup_done: false,
      step: 4,
      readiness: { numbers_checked: 41, weak_area: "Food waste" },
    });
  });

  test("a new world starts at step 1 without readiness", async () => {
    resetLearnerMock("new");
    await signIn();
    const response = await fetch(`${APP}/api/setup`);
    await expect(response.json()).resolves.toMatchObject({ setup_done: false, step: 1, readiness: null });
  });

  test("finishing needs readiness", async () => {
    resetLearnerMock("new");
    await signIn();
    const early = await fetch(`${APP}/api/setup/finish`, { method: "POST" });
    expect(early.status).toBe(409);
    resetLearnerMock("design");
    const done = await fetch(`${APP}/api/setup/finish`, { method: "POST" });
    expect(done.status).toBe(200);
  });

  test("starting while running is refused", async () => {
    await signIn();
    const response = await fetch(`${APP}/api/learning/start`, { method: "POST" });
    expect(response.status).toBe(409);
    await expect(response.json()).resolves.toMatchObject({ error: "already_learning" });
  });

  test("owner notes round-trip and clear", async () => {
    await signIn();
    const listed = (await (await fetch(`${APP}/api/owner-notes`)).json()) as { text: string };
    expect(listed.text).toContain("# Notes for Charie");
    const saved = await fetch(`${APP}/api/owner-notes`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: "My rule." }),
    });
    expect(saved.status).toBe(200);
    const again = (await (await fetch(`${APP}/api/owner-notes`)).json()) as {
      text: string;
      sorted: unknown;
    };
    expect(again.text).toBe("My rule.");
    expect(again.sorted).not.toBeNull();
    const cleared = await fetch(`${APP}/api/owner-notes`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: "   " }),
    });
    expect(cleared.status).toBe(200);
    await expect(cleared.json()).resolves.toMatchObject({ text: "", saved_at: null, sorted: null });
  });

  // Raw multipart bodies: jsdom's FormData never finishes serializing
  // through msw/node in this repo's jsdom setup, while real browsers and
  // the production path use the same formData parsing this exercises.
  function upload(name: string, size: number): { headers: Record<string, string>; body: string } {
    const boundary = "----charie-test-boundary";
    return {
      headers: { "Content-Type": `multipart/form-data; boundary=${boundary}` },
      body:
        `--${boundary}\r\n` +
        `Content-Disposition: form-data; name="file"; filename="${name}"\r\n` +
        "Content-Type: application/octet-stream\r\n\r\n" +
        "x".repeat(size) +
        `\r\n--${boundary}--\r\n`,
    };
  }

  test("documents upload validates type and size", async () => {
    await signIn();
    const bad = upload("notes.exe", 10);
    const refused = await fetch(`${APP}/api/documents`, {
      method: "POST",
      headers: bad.headers,
      body: bad.body,
    });
    expect(refused.status).toBe(400);
    await expect(refused.json()).resolves.toMatchObject({
      error: "file_type",
      message: "notes.exe can't be added. Charie reads Word, PDF, PowerPoint, Excel, Markdown and text files.",
    });
    const good = upload("extra.pdf", 10);
    const added = await fetch(`${APP}/api/documents`, {
      method: "POST",
      headers: good.headers,
      body: good.body,
    });
    expect(added.status).toBe(201);
    await expect(added.json()).resolves.toMatchObject({
      document: { file_name: "extra.pdf", file_type: "pdf", status: "new", pages: null },
    });
  });
  test("remove hides the document", async () => {
    await signIn();
    const listed = (await (await fetch(`${APP}/api/documents`)).json()) as {
      documents: { id: number; file_name: string }[];
    };
    const target = listed.documents.find((doc) => doc.file_name === "Refund policy.docx");
    expect(target).toBeDefined();
    const removed = await fetch(`${APP}/api/documents/${target!.id}`, { method: "DELETE" });
    expect(removed.status).toBe(204);
    const again = (await (await fetch(`${APP}/api/documents`)).json()) as {
      documents: { file_name: string }[];
    };
    expect(again.documents.map((doc) => doc.file_name)).not.toContain("Refund policy.docx");
  });

  test("retry only reads failed or unreadable documents", async () => {
    await signIn();
    const listed = (await (await fetch(`${APP}/api/documents`)).json()) as {
      documents: { id: number; file_name: string }[];
    };
    const learned = listed.documents.find((doc) => doc.file_name === "Finance wiki.pdf");
    const refused = await fetch(`${APP}/api/documents/${learned!.id}/retry`, { method: "POST" });
    expect(refused.status).toBe(409);
    await expect(refused.json()).resolves.toMatchObject({ error: "nothing_to_retry" });
    const unreadable = listed.documents.find(
      (doc) => doc.file_name === "Supplier contract scan.pdf",
    );
    const reading = await fetch(`${APP}/api/documents/${unreadable!.id}/retry`, {
      method: "POST",
    });
    expect(reading.status).toBe(200);
    await expect(reading.json()).resolves.toMatchObject({
      document: { status: "reading", progress: 0, unreadable_pages: 0, error: null },
    });
  });

  test("pause and resume need a running run", async () => {
    resetLearnerMock("new");
    await signIn();
    const nothing = await fetch(`${APP}/api/learning/pause`, { method: "POST" });
    expect(nothing.status).toBe(409);
    await expect(nothing.json()).resolves.toMatchObject({ error: "not_running" });
    resetLearnerMock("design");
    const paused = await fetch(`${APP}/api/learning/pause`, { method: "POST" });
    expect(paused.status).toBe(200);
    const again = await fetch(`${APP}/api/learning/pause`, { method: "POST" });
    expect(again.status).toBe(409);
    const resumed = await fetch(`${APP}/api/learning/resume`, { method: "POST" });
    expect(resumed.status).toBe(200);
    const runs = (await (await fetch(`${APP}/api/learning`)).json()) as {
      runs: { status: string }[];
    };
    expect(runs.runs[0].status).toBe("running");
  });

  test("the stream replays the run lines", async () => {
    await signIn();
    const response = await fetch(`${APP}/api/learning/stream`, {
      headers: { Accept: "text/event-stream" },
    });
    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toContain("text/event-stream");
    const reader = response.body!.getReader();
    const decoder = new TextDecoder();
    let text = "";
    for (let i = 0; i < 20; i += 1) {
      const { done, value } = await reader.read();
      if (done) break;
      text += decoder.decode(value, { stream: true });
      if (text.split("\n\n").length >= 6) break;
    }
    await reader.cancel();
    expect(text).toContain("id: 1");
    expect(text).toContain("Net sales matches the finance report");
  });});
