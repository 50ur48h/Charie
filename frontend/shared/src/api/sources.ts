import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type { LearnerDocument } from "./learner-types";

// GET /api/documents (architecture 09): all but removed, newest uploaded
// first. Polls every 2 s while a document is reading; the fake reader
// advances progress in P04.5.
export function useDocuments() {
  return useQuery({
    queryKey: ["learner-documents"],
    queryFn: ({ signal }) =>
      apiFetch<{ documents: LearnerDocument[] }>("/api/documents", { signal }),
    refetchInterval: (query) =>
      (query.state.data?.documents ?? []).some((doc) => doc.status === "reading") ? 2000 : false,
  });
}
