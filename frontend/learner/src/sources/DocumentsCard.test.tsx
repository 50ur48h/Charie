import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { Toaster, type LearnerDocument } from "@charie/shared";
import { DocumentsCard } from "./DocumentsCard";

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

function makeDoc(id: number, file_name: string): LearnerDocument {
  return {
    id,
    file_name,
    file_type: "pdf",
    size_bytes: 1024,
    pages: id,
    unreadable_pages: 0,
    fact_count: id,
    status: "learned",
    progress: null,
    error: null,
    uploaded_at: `2026-10-03T10:${String(id).padStart(2, "0")}:00+05:30`,
    learned_at: `2026-10-03T11:${String(id).padStart(2, "0")}:00+05:30`,
  };
}

// The card uploads with XHR (progress needs it). The fake holds each
// response until respond() runs and fires one progress event on send.
let pendingXhr: { respond: (status: number, body: unknown) => void } | null = null;

function stubUpload(): void {
  pendingXhr = null;
  class FakeXHR {
    upload: { onprogress: ((event: unknown) => void) | null } = { onprogress: null };
    onload: (() => void) | null = null;
    responseText = "";
    status = 0;
    open(): void {}
    send = (): void => {
      this.upload.onprogress?.({ lengthComputable: true, loaded: 50, total: 100 });
      pendingXhr = {
        respond: (status: number, body: unknown) => {
          this.status = status;
          this.responseText = JSON.stringify(body);
          this.onload?.();
        },
      };
    };
  }
  vi.stubGlobal("XMLHttpRequest", FakeXHR);
}

function stubFetch(serverDocs: LearnerDocument[]) {
  return vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    if (url.includes("/api/documents/") && method === "DELETE") {
      const id = Number(url.slice(url.lastIndexOf("/") + 1));
      const found = serverDocs.find((doc) => doc.id === id);
      if (found) found.status = "removed";
      return Promise.resolve(new Response(null, { status: 204 }));
    }
    if (url.includes("/retry") && method === "POST") {
      const id = Number(url.split("/").at(-2));
      const found = serverDocs.find((doc) => doc.id === id);
      if (found) {
        found.status = "reading";
        found.progress = 0;
        found.unreadable_pages = 0;
        found.error = null;
      }
      return Promise.resolve(json({ document: found }));
    }
    if (url.includes("/api/documents") && method === "GET") {
      return Promise.resolve(
        json({ documents: serverDocs.filter((doc) => doc.status !== "removed") }),
      );
    }
    return Promise.resolve(json({}));
  });
}

function renderCard(serverDocs: LearnerDocument[]) {
  const fetchMock = stubFetch(serverDocs);
  vi.stubGlobal("fetch", fetchMock);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <Toaster />
      <DocumentsCard />
    </QueryClientProvider>,
  );
  return fetchMock;
}

function drop(name: string): void {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  fireEvent.change(input, { target: { files: [new File(["hello"], name, { type: "application/pdf" })] } });
}

describe("DocumentsCard", () => {
  test("shows 7 rows, then all 14", async () => {
    const serverDocs = Array.from({ length: 14 }, (_, i) => makeDoc(i + 1, `Doc ${i + 1}.pdf`));
    renderCard(serverDocs);
    expect(await screen.findByText("Doc 1.pdf")).toBeTruthy();
    expect(screen.getByText("Doc 7.pdf")).toBeTruthy();
    expect(screen.queryByText("Doc 8.pdf")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Show all 14 documents" }));
    expect(screen.getByText("Doc 8.pdf")).toBeTruthy();
    expect(screen.getByText("Doc 14.pdf")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Show fewer" }));
    expect(screen.queryByText("Doc 8.pdf")).toBeNull();
  });

  test("an upload shows its progress", async () => {
    const serverDocs = [makeDoc(1, "Doc 1.pdf")];
    renderCard(serverDocs);
    await screen.findByText("Doc 1.pdf");
    stubUpload();
    drop("Extra rules.pdf");
    expect(await screen.findByText("50%")).toBeTruthy();
    pendingXhr?.respond(201, {
      document: { ...makeDoc(99, "Extra rules.pdf"), status: "new", pages: null, fact_count: 0 },
    });
    serverDocs.push({ ...makeDoc(99, "Extra rules.pdf"), status: "new", pages: null, fact_count: 0 });
    expect(await screen.findByText("New · not learned yet")).toBeTruthy();
    await waitFor(() => expect(screen.queryByText("50%")).toBeNull());
  });

  test("remove asks first", async () => {
    const serverDocs = [makeDoc(1, "Doc 1.pdf")];
    renderCard(serverDocs);
    await screen.findByText("Doc 1.pdf");
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    const dialog = await screen.findByRole("dialog", { name: "Remove Doc 1.pdf?" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.getByText("Doc 1.pdf")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    const reopened = await screen.findByRole("dialog", { name: "Remove Doc 1.pdf?" });
    fireEvent.click(within(reopened).getByRole("button", { name: "Remove" }));
    expect(await screen.findByText("Removed Doc 1.pdf.")).toBeTruthy();
    await waitFor(() => expect(screen.queryByText("Doc 1.pdf")).toBeNull());
  });

  test("retry sends the request", async () => {
    const serverDocs = [
      { ...makeDoc(1, "Scan.pdf"), unreadable_pages: 2, fact_count: 5 },
    ];
    renderCard(serverDocs);
    expect(await screen.findByText("2 pages unreadable")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Reading it again.")).toBeTruthy();
    expect(await screen.findByText("Reading")).toBeTruthy();
  });

  test("shows the empty message", async () => {
    renderCard([]);
    expect(await screen.findByText("No documents yet. Drop files here to start.")).toBeTruthy();
  });
});
