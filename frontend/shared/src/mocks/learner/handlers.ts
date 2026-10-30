import { http, HttpResponse } from "msw";
import { needSession } from "../session";
import type { DatabaseInput, LearnerDocument, LearningEvent } from "../../api/learner-types";
import { learner, saveLearner, saveSetup, setup, setupState } from "./state";
import { ensureDraft, openDraft } from "./versions";
import { getRunEvents, newestRun, subscribeRunEvents } from "./timers";

// Fake learner addresses (mock only). One handler per address; the screens
// read through the real client. Documents, notes, runs and the live feed work
// here; the reader and run clocks live in timers.ts. The draft arrives later.
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
export const LEARNER_PAUSE_URL = "*/api/learning/pause";
export const LEARNER_RESUME_URL = "*/api/learning/resume";
export const LEARNER_STREAM_URL = "*/api/learning/stream";

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

// Notes count as changed when they were saved after the newest run started,
// or when notes are saved and no run exists yet (P04.6: the banner shows).
function notesChangedSinceRun(): boolean {
  const slice = setup();
  const savedAt = slice.notes.saved_at;
  if (!savedAt) return false;
  const newest = newestRun();
  if (!newest) return true;
  return Date.parse(savedAt) > Date.parse(newest.started_at);
}

function sse(event: LearningEvent): string {
  const data = JSON.stringify({
    seq: event.seq,
    at: event.at,
    step: event.step,
    kind: event.kind,
    message: event.message,
  });
  return `id: ${event.seq}\nevent: ${event.kind}\ndata: ${data}\n\n`;
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
      version_number: ensureDraft("first_learning", "First learning").number,
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
    const store = learner();
    const count = store.documents.filter(
      (doc) => doc.status === "new" || doc.status === "reading",
    ).length;
    const notesChanged = notesChangedSinceRun();
    const reason =
      count > 0 && notesChanged
        ? `${count === 1 ? "1 new document" : `${count} new documents`} and changed notes`
        : notesChanged
          ? "changed notes"
          : count === 1
            ? "1 new document"
            : `${count} new documents`;
    const draftNote = openDraft()?.summary.note ?? null;
    const draft = ensureDraft("refresh", reason);
    store.runs.push({
      id: store.runs.reduce((max, run) => Math.max(max, run.id), 0) + 1,
      kind: "refresh",
      status: "running",
      reason: draftNote === null ? reason : `${reason} · ${draftNote}`,
      step: 1,
      percent: 0,
      minutes_left: 66,
      progress: [],
      cost_usd: 0,
      summary: null,
      version_number: draft.number,
      new_version: true,
      started_at: new Date().toISOString(),
      finished_at: null,
    });
    saveLearner();
    return HttpResponse.json({ ok: true });
  }),

  http.delete(LEARNER_DOCUMENT_URL, ({ params }) => {
    const blocked = needSession();
    if (blocked) return blocked;
    const store = learner();
    const document = store.documents.find((doc) => doc.id === Number(params.id));
    if (!document) {
      return HttpResponse.json(
        { error: "not_found", message: "Charie couldn't find that document." },
        { status: 404 },
      );
    }
    document.status = "removed";
    saveLearner();
    return new HttpResponse(null, { status: 204 });
  }),

  http.post(`${LEARNER_DOCUMENT_URL}/retry`, ({ params }) => {
    const blocked = needSession();
    if (blocked) return blocked;
    const store = learner();
    const document = store.documents.find((doc) => doc.id === Number(params.id));
    if (!document) {
      return HttpResponse.json(
        { error: "not_found", message: "Charie couldn't find that document." },
        { status: 404 },
      );
    }
    if (document.status !== "failed" && document.unreadable_pages === 0) {
      return HttpResponse.json(
        { error: "nothing_to_retry", message: "This document doesn't need another try." },
        { status: 409 },
      );
    }
    document.status = "reading";
    document.progress = 0;
    document.unreadable_pages = 0;
    document.error = null;
    saveLearner();
    return HttpResponse.json({ document });
  }),

  http.post(LEARNER_PAUSE_URL, () => {
    const blocked = needSession();
    if (blocked) return blocked;
    const run = newestRun();
    if (!run || run.status !== "running") {
      return HttpResponse.json(
        { error: "not_running", message: "There's no learning run to pause." },
        { status: 409 },
      );
    }
    run.status = "paused";
    saveLearner();
    return HttpResponse.json({ ok: true });
  }),

  http.post(LEARNER_RESUME_URL, () => {
    const blocked = needSession();
    if (blocked) return blocked;
    const run = newestRun();
    if (!run || run.status !== "paused") {
      return HttpResponse.json(
        { error: "not_paused", message: "Learning isn't paused." },
        { status: 409 },
      );
    }
    run.status = "running";
    saveLearner();
    return HttpResponse.json({ ok: true });
  }),

  http.get(LEARNER_STREAM_URL, ({ request }) => {
    const blocked = needSession();
    if (blocked) return blocked;
    const run = newestRun();
    if (!run) {
      return HttpResponse.json(
        { error: "no_run", message: "Charie hasn't started learning yet." },
        { status: 404 },
      );
    }
    const lastId = Number(request.headers.get("last-event-id") ?? 0) || 0;
    const history = getRunEvents(run.id)
      .filter((event) => event.seq > lastId)
      .slice(-20);
    const encoder = new TextEncoder();
    let stop: (() => void) | null = null;
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        for (const event of history) controller.enqueue(encoder.encode(sse(event)));
        stop = subscribeRunEvents(run.id, (event) => {
          if (event.seq > lastId) controller.enqueue(encoder.encode(sse(event)));
        });
      },
      cancel() {
        stop?.();
      },
    });
    return new HttpResponse(stream, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      },
    });
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
    return HttpResponse.json(setup().source);
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
    return HttpResponse.json(slice.source);
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
