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

// POST /api/chats/{id}/messages { text, mode, choice? } (architecture 09).
// Answering Charie's quick question sends the option's label as the text
// with its id as the choice.
export function useSendMessage() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      chatId,
      text,
      choice,
    }: {
      chatId: number;
      text: string;
      choice?: string;
    }) =>
      apiFetch<SentMessages>(`/api/chats/${chatId}/messages`, {
        method: "POST",
        body: { text, mode: "thinking", choice },
      }),
    onSuccess: (_data, { chatId }) => {
      void client.invalidateQueries({ queryKey: ["chat", chatId] });
      // Answering (even a quick choice) can resolve a waiting question.
      void client.invalidateQueries({ queryKey: ["status"] });
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
// A null vote clears a previous one and its note; the answer never changes.
export function useFeedback() {
  return useMutation({
    mutationFn: ({
      messageId,
      vote,
      note,
    }: {
      messageId: number;
      vote: FeedbackVote;
      note?: string;
    }) =>
      apiFetch<{ vote: FeedbackVote }>(`/api/messages/${messageId}/feedback`, {
        method: "POST",
        body: { vote, note },
      }),
  });
}

// POST /api/messages/{id}/wrong { correction } (architecture 09): the
// correction goes to the learner to-do list; the answer never changes here.
export function useWrongMessage() {
  return useMutation({
    mutationFn: ({ messageId, correction }: { messageId: number; correction: string }) =>
      apiFetch<{ todo_id: number }>(`/api/messages/${messageId}/wrong`, {
        method: "POST",
        body: { correction },
      }),
  });
}

// PATCH /api/chats/{id} { title } (architecture 09). A blank title never
// reaches the server: the rename dialog rejects it first.
export function useRenameChat() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ chatId, title }: { chatId: number; title: string }) =>
      apiFetch<ChatSummary>(`/api/chats/${chatId}`, {
        method: "PATCH",
        body: { title },
      }),
    onSuccess: (_data, { chatId }) => {
      void client.invalidateQueries({ queryKey: ["chats"] });
      void client.invalidateQueries({ queryKey: ["chat", chatId] });
    },
  });
}

// DELETE /api/chats/{id} (architecture 09). The server refuses a chat with
// a running answer; the caller keeps the chat and says so.
export function useDeleteChat() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (chatId: number) =>
      apiFetch<{ ok: true }>(`/api/chats/${chatId}`, { method: "DELETE" }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["chats"] });
    },
  });
}

// POST /api/messages/{id}/finish: "Finish now" (architecture 09).
export function useFinishMessage() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (messageId: number) =>
      apiFetch<{ finished: boolean; message_id: number }>(
        `/api/messages/${messageId}/finish`,
        { method: "POST" },
      ),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["chat"] });
    },
  });
}
