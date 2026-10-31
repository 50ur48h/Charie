import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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

// POST /api/learning/start: begins the first run (409 while one runs).
// On success the run list refreshes.
export function useStartLearning() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<{ ok: true }>("/api/learning/start", { method: "POST" }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["learner-learning"] });
      void client.invalidateQueries({ queryKey: ["learner-setup"] });
    },
  });
}

// POST /api/learning/refresh: starts a refresh run (409 while one runs).
export function useRefreshLearning() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<{ ok: true }>("/api/learning/refresh", { method: "POST" }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["learner-learning"] });
      void client.invalidateQueries({ queryKey: ["learner-setup"] });
      void client.invalidateQueries({ queryKey: ["learner-refresh-status"] });
    },
  });
}

// GET /api/learning/refresh-status: snapshot-based pending changes. The
// banner reads this, so removals show and failed runs keep their pending
// changes (the timestamps alone cannot tell those cases apart).
export interface RefreshStatus {
  documents: number[];
  removed: number[];
  notes_changed: boolean;
}

export function useRefreshStatus(running: boolean) {
  return useQuery({
    queryKey: ["learner-refresh-status"],
    queryFn: ({ signal }) => apiFetch<RefreshStatus>("/api/learning/refresh-status", { signal }),
    // A running refresh consumes the snapshot when it finishes; poll until
    // the run ends so the banner clears without a reload.
    refetchInterval: running ? 5000 : false,
  });
}
// POST /api/learning/pause and /resume. 409 when there is nothing to do.
export function usePauseLearning() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<{ ok: true }>("/api/learning/pause", { method: "POST" }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["learner-learning"] });
    },
  });
}

export function useResumeLearning() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<{ ok: true }>("/api/learning/resume", { method: "POST" }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["learner-learning"] });
    },
  });
}