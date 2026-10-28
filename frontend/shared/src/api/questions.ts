import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type { QuestionListResponse, QuestionStatus } from "../questions/types";

// GET /api/questions?status= (architecture 09). No status means every question.
export function useQuestions(status?: QuestionStatus) {
  return useQuery({
    queryKey: ["questions", status ?? "all"],
    queryFn: ({ signal }) =>
      apiFetch<QuestionListResponse>(
        status ? `/api/questions?status=${status}` : "/api/questions",
        { signal },
      ),
  });
}

export type AnswerPayload = { optionId: string } | { text: string };

// POST /api/questions/{id}/answer { option_id } or { text } (architecture 09):
// exactly one of the two; text is trimmed and never empty.
export function useAnswerQuestion() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ questionId, answer }: { questionId: number; answer: AnswerPayload }) => {
      const body =
        "optionId" in answer
          ? { option_id: answer.optionId }
          : { text: answer.text.trim() };
      return apiFetch<{ ok: true }>(`/api/questions/${questionId}/answer`, {
        method: "POST",
        body,
      });
    },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["questions"] });
      void client.invalidateQueries({ queryKey: ["status"] });
    },
  });
}

// POST /api/questions/{id}/skip (architecture 09). Skipping keeps the
// documented default; it never claims the default is owner-confirmed.
export function useSkipQuestion() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (questionId: number) =>
      apiFetch<{ ok: true }>(`/api/questions/${questionId}/skip`, { method: "POST" }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["questions"] });
      void client.invalidateQueries({ queryKey: ["status"] });
    },
  });
}
