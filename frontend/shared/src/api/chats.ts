import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";
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
  return useMutation({
    mutationFn: ({ chatId, text }: { chatId: number; text: string }) =>
      apiFetch<SentMessages>(`/api/chats/${chatId}/messages`, {
        method: "POST",
        body: { text, mode: "thinking" },
      }),
  });
}
