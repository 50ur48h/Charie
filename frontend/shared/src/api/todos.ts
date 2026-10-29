import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type { LearnerTodo } from "./learner-types";

// The learner's to-do list (P04.9): corrections from chats and words to
// check. Dismissing marks one dismissed; the entry itself never changes.

// GET /api/todos: the open items, newest first.
export function useTodos() {
  return useQuery({
    queryKey: ["learner-todos"],
    queryFn: ({ signal }) => apiFetch<{ todos: LearnerTodo[] }>("/api/todos", { signal }),
  });
}

// POST /api/todos/{id}/dismiss. 404 for an unknown id.
export function useDismissTodo() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      apiFetch<{ todo: LearnerTodo }>(`/api/todos/${id}/dismiss`, { method: "POST" }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["learner-todos"] });
    },
  });
}
