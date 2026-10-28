import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./client";

export interface Status {
  questions_waiting: number;
  data_through: string | null;
}

export function useStatus() {
  return useQuery({
    queryKey: ["status"],
    queryFn: ({ signal }) => apiFetch<Status>("/api/status", { signal }),
  });
}
