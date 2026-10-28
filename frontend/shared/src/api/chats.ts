import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, apiFetch } from "./client";
import type { Chat } from "./chat-types";
import type { ChatSummary } from "./types";

// POST /api/chats answers the created chat's summary (P03.1 defines this
// shape: the back end must send exactly it).
export function useCreateChat() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<ChatSummary>("/api/chats", { method: "POST" }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["chats"] });
    },
  });
}

export interface SentMessages {
  user_message_id: number;
  assistant_message_id: number;
}

// POST /api/chats/{id}/messages { text, mode } (architecture 09).
export function useSendMessage() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ chatId, text }: { chatId: number; text: string }) =>
      apiFetch<SentMessages>(`/api/chats/${chatId}/messages`, {
        method: "POST",
        body: { text, mode: "thinking" },
      }),
    onSuccess: (_data, { chatId }) => {
      void client.invalidateQueries({ queryKey: ["chat", chatId] });
    },
  });
}

// GET /api/chats/{id}: one chat with its messages (architecture 09).
export function useChat(chatId: number) {
  return useQuery({
    queryKey: ["chat", chatId],
    queryFn: ({ signal }) => apiFetch<Chat>(`/api/chats/${chatId}`, { signal }),
    retry: (count, error) =>
      error instanceof ApiError && error.status === 404 ? false : count < 1,
  });
}

export type FeedbackVote = "up" | "down" | null;

// POST /api/messages/{id}/feedback { vote, note? } (architecture 09).
// A null vote clears a previous one; the note stays unused for now.
export function useFeedback() {
  return useMutation({
    mutationFn: ({ messageId, vote }: { messageId: number; vote: FeedbackVote }) =>
      apiFetch<{ ok: true }>(`/api/messages/${messageId}/feedback`, {
        method: "POST",
        body: { vote },
      }),
  });
}

// POST /api/messages/{id}/wrong { correction } (architecture 09): the
// correction goes to the learner to-do list; the answer never changes here.
export function useWrongMessage() {
  return useMutation({
    mutationFn: ({ messageId, correction }: { messageId: number; correction: string }) =>
      apiFetch<{ ok: true }>(`/api/messages/${messageId}/wrong`, {
        method: "POST",
        body: { correction },
      }),
  });
}

// POST /api/messages/{id}/finish: "Finish now" (architecture 09).
export function useFinishMessage() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (messageId: number) =>
      apiFetch<{ ok: true }>(`/api/messages/${messageId}/finish`, { method: "POST" }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["chat"] });
    },
  });
}
