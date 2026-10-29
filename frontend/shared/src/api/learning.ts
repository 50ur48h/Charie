import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type { LearningOverview } from "./learner-types";

// GET /api/learning (architecture 09): runs, newest first. Polls every 5 s
// while the newest run is running; the live feed arrives in P04.7.
export function useLearning() {
  return useQuery({
    queryKey: ["learner-learning"],
    queryFn: ({ signal }) => apiFetch<LearningOverview>("/api/learning", { signal }),
    refetchInterval: (query) =>
      query.state.data?.runs?.[0]?.status === "running" ? 5000 : false,
  });
}
