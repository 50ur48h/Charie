import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type { KbChange, KbVersion } from "./learner-types";

// GET /api/versions (architecture 09, learner addresses).
export function useVersions() {
  return useQuery({
    queryKey: ["learner-versions"],
    queryFn: ({ signal }) =>
      apiFetch<{ versions: KbVersion[]; live: number | null; draft: number | null }>(
        "/api/versions",
        { signal },
      ),
  });
}

// GET /api/versions/{id}/changes, with which version it is.
export function useVersionChanges(versionId: number | null) {
  return useQuery({
    queryKey: ["learner-changes", versionId],
    queryFn: ({ signal }) =>
      apiFetch<{ version: number; status: string; changes: KbChange[] }>(
        `/api/versions/${versionId}/changes`,
        { signal },
      ),
    enabled: versionId !== null,
  });
}

// POST /api/versions/{number}/publish. 409 for a live version or big changes.
export function usePublishVersion() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (versionNumber: number) =>
      apiFetch<{ version: KbVersion }>(`/api/versions/${versionNumber}/publish`, {
        method: "POST",
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["knowledge"] });
      void client.invalidateQueries({ queryKey: ["knowledge-entry"] });
      void client.invalidateQueries({ queryKey: ["learner-versions"] });
      void client.invalidateQueries({ queryKey: ["learner-changes"] });
      void client.invalidateQueries({ queryKey: ["learner-setup"] });
    },
  });
}
