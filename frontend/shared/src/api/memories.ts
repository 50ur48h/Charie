import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";

// One remembered preference (architecture 09 GET /api/memories). The
// real addresses serve these shapes; the fake API mirrors them so the
// Settings screen works in mock mode.
export interface Memory {
  id: number;
  text: string;
  source: string;
  saved_at: string;
}

// GET /api/memories.
export function useMemories() {
  return useQuery({
    queryKey: ["memories"],
    queryFn: ({ signal }) => apiFetch<Memory[]>("/api/memories", { signal }),
  });
}

// DELETE /api/memories/{id}: forget one memory.
export function useDeleteMemory() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => apiFetch<{ ok: true }>(`/api/memories/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["memories"] });
    },
  });
}

// DELETE /api/memories: forget everything.
export function useClearMemories() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<{ ok: true }>("/api/memories", { method: "DELETE" }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["memories"] });
    },
  });
}
