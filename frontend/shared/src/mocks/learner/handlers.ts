import { http, HttpResponse } from "msw";
import { needSession } from "../session";
import type { DatabaseInput, LearnerDocument } from "../../api/learner-types";
import { learner, saveLearner, saveSetup, setup, setupState } from "./state";

// Fake learner addresses (mock only). One handler per address; the screens
// read through the real client. Documents upload (with progress) and notes
// saving work here; timers, the draft and run progress arrive later.
export const LEARNER_DOCUMENTS_URL = "*/api/documents";
export const LEARNER_DOCUMENT_URL = "*/api/documents/:id";
export const LEARNER_LEARNING_URL = "*/api/learning";
export const LEARNER_SETUP_URL = "*/api/setup";
export const LEARNER_FINISH_URL = "*/api/setup/finish";
export const LEARNER_DATABASE_URL = "*/api/sources/database";
export const LEARNER_DATABASE_TEST_URL = "*/api/sources/database/test";
export const LEARNER_NOTES_URL = "*/api/owner-notes";
export const LEARNER_START_URL = "*/api/learning/start";
export const LEARNER_REFRESH_URL = "*/api/learning/refresh";

const delay = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

function saveFailedLogin(
  body: unknown,
): { error: "cant_connect" | "login_failed" | "not_read_only"; message: string } | null {
  const input = (body ?? {}) as { host?: unknown; username?: unknown; password?: unknown };
  if (typeof input.host === "string" && input.host.includes("wrong")) {
    return {
      error: "cant_connect",
      message: "Charie couldn't reach this server. Check the server address and port.",
    };
  }
  if (input.password === "wrong") {
    return { error: "login_failed", message: "The username or password is wrong." };
  }
  if (input.username === "admin") {
    return {
      error: "not_read_only",
      message: "This login can change data. Please use a read-only login.",
    };
  }
  return null;
}

// "bella_forno" -> "Bella Forno database".
export function databaseName(database: string): string {
  const words = database
    .split(/[_-]+/)
    .filter(Boolean)
    .map((word) => word[0].toUpperCase() + word.slice(1));
  return `${words.join(" ")} database`;
}

const LEARNABLE_EXTENSIONS = new Set(["docx", "pdf", "pptx", "xlsx", "md", "txt"]);

export function checkFile(name: string, size: number): { error: "file_type" | "file_too_big"; message: string } | null {
  const ext = name.slice(name.lastIndexOf(".") + 1).toLowerCase();
  if (!LEARNABLE_EXTENSIONS.has(ext)) {
    return {
      error: "file_type",
      message: `${name} can't be added. Charie reads Word, PDF, PowerPoint, Excel, Markdown and text files.`,
    };
  }
  if (size > 50 * 1024 * 1024) {
    return {
      error: "file_too_big",
      message: `${name} is too big. Each file can be up to 50 MB.`,
    };
  }
  return null;
}

function runningRun(): boolean {
  return learner().runs.some((run) => run.status === "running" || run.status === "paused");
}

export const learnerHandlers = [
  http.get(LEARNER_DOCUMENTS_URL, () => {
    const blocked = needSession();
    if (blocked) return blocked;
    const documents = learner()
      .documents.filter((doc) => doc.status !== "removed")
      .sort((a, b) => Date.parse(b.uploaded_at) - Date.parse(a.uploaded_at));
    return HttpResponse.json({ documents });
  }),

  http.post(LEARNER_DOCUMENTS_URL, async ({ request }) => {
    const blocked = needSession();
    if (blocked) return blocked;
    const form = await request.formData();
    // Duck-typed on purpose: the parsed part and this realm's File can come
    // from different globals (jsdom vs undici), so instanceof lies.
    const part = form.get("file") as { name?: unknown; size?: unknown } | null;
    const upload =
      typeof part === "object" && part !== null && typeof part.name === "string" && typeof part.size === "number"
        ? { name: part.name, size: part.size }
        : null;
    if (upload === null) {
      return HttpResponse.json({ error: "file_type", message: "Choose a file first." }, { status: 400 });
    }
    const failed = checkFile(upload.name, upload.size);
    if (failed) {
      return HttpResponse.json(failed, { status: 400 });
    }
    const store = learner();
    const document: LearnerDocument = {
      id: store.documents.reduce((max, doc) => Math.max(max, doc.id), 0) + 1,
      file_name: upload.name,
      file_type: upload.name.slice(upload.name.lastIndexOf(".") + 1).toLowerCase(),
      size_bytes: upload.size,
      pages: null,
      unreadable_pages: 0,
      fact_count: 0,
      status: "new",
      progress: null,
      error: null,
      uploaded_at: new Date().toISOString(),
      learned_at: null,
    };
    store.documents.push(document);
    saveLearner();
    return HttpResponse.json({ document }, { status: 201 });
  }),

  http.get(LEARNER_LEARNING_URL, () => {
    const blocked = needSession();
    if (blocked) return blocked;
    const runs = [...learner().runs].sort(
      (a, b) => Date.parse(b.started_at) - Date.parse(a.started_at),
    );
    return HttpResponse.json({ runs });
  }),

  http.post(LEARNER_START_URL, () => {
    const blocked = needSession();
    if (blocked) return blocked;
    if (runningRun()) {
      return HttpResponse.json(
        { error: "already_learning", message: "Charie is already learning." },
        { status: 409 },
      );
    }
    const store = learner();
    store.runs.push({
      id: store.runs.reduce((max, run) => Math.max(max, run.id), 0) + 1,
      kind: "first",
      status: "running",
      reason: null,
      step: 1,
      percent: 0,
      minutes_left: 66,
      progress: Array.from({ length: 12 }, (_, i) => ({ step: i + 1, done: 0, total: null, note: "Waiting" })),
      cost_usd: 0,
      summary: null,
      version_number: 1,
      new_version: true,
      started_at: new Date().toISOString(),
      finished_at: null,
    });
    saveLearner();
    return HttpResponse.json({ ok: true });
  }),

  http.post(LEARNER_REFRESH_URL, () => {
    const blocked = needSession();
    if (blocked) return blocked;
    if (runningRun()) {
      return HttpResponse.json(
        {
          error: "already_learning",
          message: "Charie is already learning. Try again when this run is done.",
        },
        { status: 409 },
      );
    }
    const slice = setup();
    const store = learner();
    const count = store.documents.filter(
      (doc) => doc.status === "new" || doc.status === "reading",
    ).length;
    store.runs.push({
      id: store.runs.reduce((max, run) => Math.max(max, run.id), 0) + 1,
      kind: "refresh",
      status: "running",
      reason: count === 1 ? "1 new document" : `${count} new documents`,
      step: 1,
      percent: 0,
      minutes_left: 66,
      progress: [],
      cost_usd: 0,
      summary: null,
      version_number: slice.draftNumber ?? (slice.liveNumber ?? 0) + 1,
      new_version: true,
      started_at: new Date().toISOString(),
      finished_at: null,
    });
    saveLearner();
    return HttpResponse.json({ ok: true });
  }),

  http.get(LEARNER_SETUP_URL, () => {
    const blocked = needSession();
    if (blocked) return blocked;
    return HttpResponse.json(setupState());
  }),

  http.post(LEARNER_FINISH_URL, () => {
    const blocked = needSession();
    if (blocked) return blocked;
    const slice = setup();
    if (!slice.readiness) {
      return HttpResponse.json(
        { error: "not_ready", message: "Charie hasn't finished learning yet." },
        { status: 409 },
      );
    }
    slice.setupDone = true;
    saveSetup();
    return HttpResponse.json({ setup_done: true });
  }),

  http.get(LEARNER_DATABASE_URL, () => {
    const blocked = needSession();
    if (blocked) return blocked;
    return HttpResponse.json({ source: setup().source });
  }),

  http.put(LEARNER_DATABASE_URL, async ({ request }) => {
    const blocked = needSession();
    if (blocked) return blocked;
    const body = (await request.json().catch(() => undefined)) as DatabaseInput | undefined;
    const failed = saveFailedLogin(body);
    if (failed) {
      await delay(900);
      return HttpResponse.json(failed, { status: 400 });
    }
    await delay(900);
    const slice = setup();
    const input = (body ?? {}) as Partial<DatabaseInput>;
    if (typeof input.password === "string" && input.password !== "") {
      slice.password = input.password;
    }
    slice.source = {
      kind: "postgres",
      name: databaseName(typeof input.database === "string" ? input.database : ""),
      host: typeof input.host === "string" ? input.host : "",
      port: typeof input.port === "number" ? input.port : 5432,
      database: typeof input.database === "string" ? input.database : "",
      username: typeof input.username === "string" ? input.username : "",
      status: "connected",
      read_only_ok: true,
      data_through: "2026-10-26",
      checked_at: new Date().toISOString(),
      details: { tables: 57, rows: 2400000 },
    };
    saveSetup();
    return HttpResponse.json({ source: slice.source });
  }),

  http.post(LEARNER_DATABASE_TEST_URL, async ({ request }) => {
    const blocked = needSession();
    if (blocked) return blocked;
    const body = (await request.json().catch(() => undefined)) as DatabaseInput | undefined;
    const failed = saveFailedLogin(body);
    await delay(900);
    if (failed) {
      return HttpResponse.json(failed, { status: 400 });
    }
    return HttpResponse.json({
      read_only_ok: true,
      data_through: "2026-10-26",
      details: { tables: 57, rows: 2400000 },
    });
  }),

  http.get(LEARNER_NOTES_URL, () => {
    const blocked = needSession();
    if (blocked) return blocked;
    return HttpResponse.json(setup().notes);
  }),

  http.put(LEARNER_NOTES_URL, async ({ request }) => {
    const blocked = needSession();
    if (blocked) return blocked;
    const body = (await request.json().catch(() => undefined)) as { text?: unknown };
    const text = typeof body?.text === "string" ? body.text : "";
    const slice = setup();
    if (text.trim() === "") {
      slice.notes = { text: "", saved_at: null, sorted: null, sorted_at: null };
    } else {
      slice.notes = { ...slice.notes, text, saved_at: new Date().toISOString() };
    }
    saveSetup();
    return HttpResponse.json(slice.notes);
  }),
];
