import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { DocumentsStep } from "./DocumentsStep";
import type { LearnerDocument } from "@charie/shared";

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

const NEW_DOC: LearnerDocument = {
  id: 99,
  file_name: "Extra rules.pdf",
  file_type: "pdf",
  size_bytes: 2048,
  pages: null,
  unreadable_pages: 0,
  fact_count: 0,
  status: "new",
  progress: null,
  error: null,
  uploaded_at: "2025-10-27T21:00:00+05:30",
  learned_at: null,
};

// The step uploads with XHR (progress needs it). The fake holds the
// response until respond() runs, so "Adding…" stays visible deterministically.
let pendingXhr: { respond: (status: number, body: unknown) => void } | null = null;

function stubUpload(serverDocs: LearnerDocument[]): void {
  pendingXhr = null;
  class FakeXHR {
    upload: { onprogress: null } = { onprogress: null };
    onload: (() => void) | null = null;
    onerror: (() => void) | null = null;
    responseText = "";
    status = 0;
    open(): void {}
    send = (): void => {
      pendingXhr = {
        respond: (status: number, body: unknown) => {
          if (body !== null) serverDocs.push(NEW_DOC);
          this.status = status;
          this.responseText = JSON.stringify(body);
          this.onload?.();
        },
      };
    };
  }
  vi.stubGlobal("XMLHttpRequest", FakeXHR);
}

function stubFetch(serverDocs: LearnerDocument[], notesText: { text: string }) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      if (url.includes("/api/documents") && method === "GET") {
        return Promise.resolve(json({ documents: serverDocs }));
      }
      if (url.includes("/api/owner-notes") && method === "GET") {
        return Promise.resolve(
          json({ text: notesText.text, saved_at: null, sorted: null, sorted_at: null }),
        );
      }
      if (url.includes("/api/owner-notes") && method === "PUT") {
        return Promise.resolve(json(JSON.parse(String(init?.body)))).then(
          async (response) => {
            const body = (await response.json()) as { text: string };
            notesText.text = body.text;
            return json({
              text: body.text,
              saved_at: new Date().toISOString(),
              sorted: null,
              sorted_at: null,
            });
          },
        );
      }
      return Promise.resolve(json({}));
    }),
  );
}

function renderStep() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <DocumentsStep onBack={() => {}} onNext={() => {}} />
    </QueryClientProvider>,
  );
}

function drop(name: string, type: string): void {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  fireEvent.change(input, { target: { files: [new File(["hello"], name, { type })] } });
}

describe("DocumentsStep", () => {
  test("an upload shows Adding, then Added", async () => {
    const serverDocs: LearnerDocument[] = [];
    stubUpload(serverDocs);
    stubFetch(serverDocs, { text: "" });
    renderStep();
    await screen.findByText("Add notes");
    drop("Extra rules.pdf", "application/pdf");
    expect(await screen.findByText(/Adding/)).toBeTruthy();
    pendingXhr?.respond(201, { document: NEW_DOC });
    expect(await screen.findByText("Extra rules.pdf")).toBeTruthy();
    await waitFor(() => expect(screen.queryByText(/Adding/)).toBeNull());
    expect(screen.getByText("Added")).toBeTruthy();
  });

  test("a .exe shows the message and never uploads", async () => {
    const serverDocs: LearnerDocument[] = [];
    stubUpload(serverDocs);
    stubFetch(serverDocs, { text: "" });
    renderStep();
    await screen.findByText("Add notes");
    drop("run.exe", "application/octet-stream");
    expect(
      await screen.findByText(
        "run.exe can't be added. Charie reads Word, PDF, PowerPoint, Excel, Markdown and text files.",
      ),
    ).toBeTruthy();
    expect(serverDocs).toEqual([]);
    expect(pendingXhr).toBeNull();
  });

  test("shows Notes added after saving", async () => {
    const notesText = { text: "" };
    stubUpload([]);
    stubFetch([], notesText);
    renderStep();
    fireEvent.click(await screen.findByRole("button", { name: "Add notes" }));
    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "Never convert currencies." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save notes" }));
    expect(await screen.findByText("Notes added")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Edit notes" })).toBeTruthy();
  });
});
