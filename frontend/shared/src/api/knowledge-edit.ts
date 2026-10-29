import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type { KnowledgeEntry } from "../knowledge/types";
import type { LearnerTodo } from "./learner-types";

// Editing the draft (P04.8/9): PATCH one entry, approve it, or mark it wrong.
// Each fix makes a draft from the live entries when there is none.

// PATCH /api/knowledge/{key} with the title and/or meaning. Makes a draft
// when there is none; 404 for an unknown key.
export function useEditEntry() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ key, title, meaning }: { key: string; title?: string; meaning?: string }) =>
      apiFetch<{ entry: KnowledgeEntry }>(`/api/knowledge/${encodeURIComponent(key)}`, {
        method: "PATCH",
        body: { title, meaning },
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["knowledge"] });
      void client.invalidateQueries({ queryKey: ["knowledge-entry"] });
      void client.invalidateQueries({ queryKey: ["learner-versions"] });
      void client.invalidateQueries({ queryKey: ["learner-changes"] });
    },
  });
}

// POST /api/knowledge/{key}/approve. 404 for an unknown key.
export function useApproveEntry() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (key: string) =>
      apiFetch<{ entry: KnowledgeEntry }>(`/api/knowledge/${encodeURIComponent(key)}/approve`, {
        method: "POST",
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["knowledge"] });
      void client.invalidateQueries({ queryKey: ["knowledge-entry"] });
      void client.invalidateQueries({ queryKey: ["learner-versions"] });
      void client.invalidateQueries({ queryKey: ["learner-changes"] });
    },
  });
}

// POST /api/knowledge/{key}/wrong with the note. Adds a to-do.
export function useMarkWrong() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ key, note }: { key: string; note: string | null }) =>
      apiFetch<{ todo: LearnerTodo }>(`/api/knowledge/${encodeURIComponent(key)}/wrong`, {
        method: "POST",
        body: { note },
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["learner-todos"] });
    },
  });
}
