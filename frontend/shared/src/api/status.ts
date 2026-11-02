import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type { Spending } from "./usage";

export interface StatusKnowledge {
  version: number | null;
  entries: number;
  documents: number;
  published_at: string | null;
}

export interface StatusData {
  name: string;
  kind: string;
  status: string;
  data_through: string | null;
}

export interface StatusLearning {
  status: string;
  step_title: string | null;
  percent: number;
}

export interface Status {
  knowledge: StatusKnowledge;
  data: StatusData | null;
  learning: StatusLearning | null;
  spending: Spending | null;
  questions_waiting: number;
  learner_url: string | null;
}

export function useStatus() {
  return useQuery({
    queryKey: ["status"],
    queryFn: ({ signal }) => apiFetch<Status>("/api/status", { signal }),
    refetchInterval: 30000,
    refetchOnWindowFocus: true,
  });
}
