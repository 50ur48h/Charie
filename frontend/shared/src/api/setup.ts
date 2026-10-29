import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type { SetupState } from "./learner-types";

// GET /api/setup: the guide's state (step 1–5, readiness or null).
export function useSetup() {
  return useQuery({
    queryKey: ["learner-setup"],
    queryFn: ({ signal }) => apiFetch<SetupState>("/api/setup", { signal }),
  });
}

// POST /api/setup/finish: marks setup done and publishes version 1.
// On success every learner query and /api/me refresh.
export function useFinishSetup() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<{ setup_done: true }>("/api/setup/finish", { method: "POST" }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["learner-setup"] });
      void client.invalidateQueries({ queryKey: ["learner-documents"] });
      void client.invalidateQueries({ queryKey: ["learner-learning"] });
      void client.invalidateQueries({ queryKey: ["questions"] });
      void client.invalidateQueries({ queryKey: ["me"] });
    },
  });
}
