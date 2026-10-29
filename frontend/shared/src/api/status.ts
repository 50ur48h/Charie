import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type { Spending } from "./usage";

export interface Status {
  questions_waiting: number;
  data_through: string | null;
  spending: Spending;
}

export function useStatus() {
  return useQuery({
    queryKey: ["status"],
    queryFn: ({ signal }) => apiFetch<Status>("/api/status", { signal }),
  });
}
