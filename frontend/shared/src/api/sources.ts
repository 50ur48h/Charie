import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type {
  ConnectionTest,
  DatabaseInput,
  DatabaseSource,
  LearnerDocument,
  OwnerNotes,
} from "./learner-types";

// GET /api/documents (architecture 09): all but removed, newest uploaded
// first. Polls every 2 s while a document is new or reading, so an upload
// is seen moving to Reading and Learned without a reload.
export function useDocuments() {
  return useQuery({
    queryKey: ["learner-documents"],
    queryFn: ({ signal }) =>
      apiFetch<{ documents: LearnerDocument[] }>("/api/documents", { signal }),
    refetchInterval: (query) =>
      (query.state.data?.documents ?? []).some(
        (doc) => doc.status === "new" || doc.status === "reading",
      ) ? 2000 : false,
  });
}

// GET /api/sources/database: the saved connection, or null when none.
export function useDatabaseSource() {
  return useQuery({
    queryKey: ["learner-database"],
    queryFn: ({ signal }) =>
      apiFetch<DatabaseSource | null>("/api/sources/database", { signal }),
  });
}

// POST /api/sources/database/test. The panel shows the result or the API's
// message; nothing is saved.
export function useTestDatabase() {
  return useMutation({
    mutationFn: (input: DatabaseInput) =>
      apiFetch<ConnectionTest>("/api/sources/database/test", { method: "POST", body: input }),
  });
}

// PUT /api/sources/database. An empty password keeps the saved one.
export function useSaveDatabase() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: DatabaseInput) =>
      apiFetch<DatabaseSource>("/api/sources/database", { method: "PUT", body: input }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["learner-database"] });
      void client.invalidateQueries({ queryKey: ["learner-setup"] });
    },
  });
}

// Upload one file with XHR so the Sources page can show progress (P04.5).
// Resolves with the new document; rejects with the API's message.
export function uploadDocument(file: File, onProgress?: (percent: number) => void): Promise<LearnerDocument> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", "/api/documents");
    request.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress?.(Math.round((event.loaded / event.total) * 100));
    };
    request.onload = () => {
      try {
        const data = JSON.parse(request.responseText) as
          | { document: LearnerDocument }
          | { error: string; message: string };
        if (request.status >= 200 && request.status < 300 && "document" in data) {
          onProgress?.(100);
          resolve(data.document);
        } else {
          reject(new Error("message" in data ? data.message : "Couldn't add that file."));
        }
      } catch {
        reject(new Error("Couldn't add that file."));
      }
    };
    request.onerror = () => reject(new Error("Couldn't reach Charie. Check your connection and try again."));
    const form = new FormData();
    form.append("file", file, file.name);
    request.send(form);
  });
}

// GET /api/owner-notes and PUT /api/owner-notes { text }. The same hooks
// back the setup step and the Sources notes card (P04.6).
export function useOwnerNotes() {
  return useQuery({
    queryKey: ["learner-notes"],
    queryFn: ({ signal }) => apiFetch<OwnerNotes>("/api/owner-notes", { signal }),
  });
}

export function useSaveOwnerNotes() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (text: string) =>
      apiFetch<OwnerNotes>("/api/owner-notes", { method: "PUT", body: { text } }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["learner-notes"] });
      void client.invalidateQueries({ queryKey: ["learner-refresh-status"] });
      void client.invalidateQueries({ queryKey: ["learner-setup"] });
    },
  });
}
// DELETE /api/documents/{id}. The list refreshes; the row is gone for good.
export function useRemoveDocument() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => apiFetch<void>(`/api/documents/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["learner-documents"] });
      void client.invalidateQueries({ queryKey: ["learner-refresh-status"] });
      void client.invalidateQueries({ queryKey: ["learner-setup"] });
    },
  });
}

// POST /api/documents/{id}/retry. Reading starts again, even with no run.
export function useRetryDocument() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      apiFetch<{ document: LearnerDocument }>(`/api/documents/${id}/retry`, { method: "POST" }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["learner-documents"] });
      void client.invalidateQueries({ queryKey: ["learner-refresh-status"] });
      void client.invalidateQueries({ queryKey: ["learner-setup"] });
    },
  });
}