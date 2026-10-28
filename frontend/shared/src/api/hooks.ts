import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type { ChatSummary, Me } from "./types";

export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: ({ signal }) => apiFetch<Me>("/api/me", { signal }),
  });
}

export function useChats() {
  return useQuery({
    queryKey: ["chats"],
    queryFn: ({ signal }) => apiFetch<ChatSummary[]>("/api/chats", { signal }),
  });
}
