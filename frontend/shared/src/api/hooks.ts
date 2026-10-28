import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, apiFetch } from "./client";
import { readSavedTheme } from "../theme/theme";
import type { ChatSummary, Me } from "./types";

export function loggedOutMe(): Me {
  return { logged_in: false, setup_done: false, theme: readSavedTheme() };
}

function isUnauthorized(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401;
}

export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: async ({ signal }) => {
      try {
        return await apiFetch<Me>("/api/me", { signal });
      } catch (error) {
        // 09: /api/me needs login too, so a 401 means logged out, not broken.
        if (isUnauthorized(error)) return loggedOutMe();
        throw error;
      }
    },
  });
}

export function useChats() {
  return useQuery({
    queryKey: ["chats"],
    queryFn: ({ signal }) => apiFetch<ChatSummary[]>("/api/chats", { signal }),
  });
}

export function useLogin() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (password: string) =>
      apiFetch<{ ok: true }>("/api/login", { method: "POST", body: { password } }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["me"] });
    },
  });
}

export function useLogout() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<{ ok: true }>("/api/logout", { method: "POST" }),
    onSuccess: () => {
      client.setQueryData<Me>(["me"], loggedOutMe());
    },
  });
}
